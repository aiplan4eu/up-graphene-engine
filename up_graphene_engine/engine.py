from concurrent import futures

import logging
from typing import Iterator, Optional, Tuple, Union
import grpc
from queue import Queue
from threading import Lock

import up_graphene_engine.grpc_io.graphene_engine_pb2 as ge_pb2
import up_graphene_engine.grpc_io.graphene_engine_pb2_grpc as ge_pb2_grpc

# Can't import the unified_planning Protobuf{Reader/Writer} because it causes
# the same grpc names to be defined more than once; and this is not allowed
from up_graphene_engine.grpc_io.proto_reader import ProtobufReader
from up_graphene_engine.grpc_io.proto_writer import ProtobufWriter

import unified_planning as up
from unified_planning.model import Problem
from unified_planning.engines import OptimalityGuarantee, CompilationKind, PlanGenerationResult,\
    ValidationResult, CompilerResult, PlanGenerationResultStatus
from unified_planning.exceptions import UPUsageError
from unified_planning.plans import Plan

class MetaSingletonGrapheneEngine(type):
    _instances = {}
    def __call__(cls, port):
        return cls._instances.setdefault(port, super(MetaSingletonGrapheneEngine, cls).__call__(port))

class GrapheneEngine(ge_pb2_grpc.GrapheneEngineServicer, metaclass=MetaSingletonGrapheneEngine):

    def __init__(self, port = 8061):
        self.port = port

        # Same explanation of attributes applies to all the operation modes below
        # Queue of requests
        self._oneshot_problems: Queue[Tuple[Problem, OptimalityGuarantee]] = Queue()
        # Queue of results
        self._oneshot_results: Queue[PlanGenerationResult] = Queue()
        # The problem being currently solved, used to correctly parse the result
        self._oneshot_problem: Optional[Problem] = None
        # The lock, used to avoid possible race conditions over the 2 queues
        self._oneshot_lock: Lock = Lock()

        self._anytime_problems: Queue[Tuple[Problem, OptimalityGuarantee]] = Queue()
        self._anytime_results: Queue[Iterator[PlanGenerationResult]] = Queue()
        self._anytime_problem: Optional[Problem] = None
        self._anytime_stop: Optional[Queue] = None
        self._anytime_lock: Lock = Lock()

        self._validate_problems: Queue[Tuple[Problem, Plan]] = Queue()
        self._validate_results: Queue[ValidationResult] = Queue()
        self._validate_lock: Lock = Lock()

        self._compile_problems: Queue[Tuple[Problem, CompilationKind]] = Queue()
        self._compile_results: Queue[CompilerResult] = Queue()
        self._compile_problem: Optional[Problem] = None
        self._compile_lock: Lock = Lock()

        self.log_format = (
            '[%(asctime)s] %(levelname)-8s %(name)-12s %(message)s')
        self.logger = logging.getLogger("UP Graphene Engine")
        logging.basicConfig(level=logging.INFO, format=self.log_format)

        self.reader = ProtobufReader()
        self.writer = ProtobufWriter()

        # Start the server
        connection = '0.0.0.0:%d' % (self.port)
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        ge_pb2_grpc.add_GrapheneEngineServicer_to_server(self, self.server)
        self.server.add_insecure_port(connection)
        self.server.start()
        self.logger.info("server started on %s" % connection)

    # Engine methods
    def solve(self, problem: Problem, optimality_guarantee: Optional[Union[OptimalityGuarantee, str]] = None) -> PlanGenerationResult:
        guarantee: OptimalityGuarantee = _normalize_optimality_guarantee(problem, optimality_guarantee)

        self._oneshot_lock.acquire()
        assert self._oneshot_problem is None
        self._oneshot_problem = problem
        self._oneshot_problems.put((problem, guarantee))
        res = self._oneshot_results.get(block=True)
        self._oneshot_problem = None
        self._oneshot_lock.release()

        return res

    def get_solutions(self, problem: Problem, optimality_guarantee: Optional[Union[OptimalityGuarantee, str]] = None) -> Iterator[PlanGenerationResult]:
        guarantee: OptimalityGuarantee = _normalize_optimality_guarantee(problem, optimality_guarantee)

        self._anytime_lock.acquire()
        assert self._anytime_problem is None
        self._anytime_problem = problem
        assert self._anytime_stop is None
        self._anytime_stop = Queue()
        self._anytime_problems.put((problem, guarantee))
        res = self._anytime_results.get(block=True)
        self._anytime_problem = None
        self._anytime_stop = None
        self._anytime_lock.release()

        return res

    def validate(self, problem: Problem, plan: Plan) -> ValidationResult:

        self._validate_lock.acquire()
        self._validate_problems.put((problem, plan))
        res = self._validate_results.get(block=True)
        self._validate_lock.release()

        return res

    def compile(self, problem: Problem, compilation_kind: CompilationKind = CompilationKind.GROUNDING) -> CompilerResult:
        compilation: CompilationKind = _normalize_compilation_kind(compilation_kind)

        if compilation != CompilationKind.GROUNDING:
            raise NotImplementedError("Currently, only grounding is supported using GRPC.")

        self._compile_lock.acquire()
        assert self._compile_problem is None
        self._compile_problem = problem
        self._compile_problems.put((problem, compilation))
        res = self._compile_results.get(block=True)
        self._compile_problem = None
        self._compile_lock.release()

        return res

    # GRPC methods
    def producePlanOneShot(self, request, context):
        # Wait on the queue, populated by the self.solve method
        problem, guarantee = self._oneshot_problems.get(block=True)
        guarantee_name = guarantee.name
        if guarantee_name == "SATISFICING":
            guarantee_name = "SATISFIABLE"
        plan_request = ge_pb2.PlanRequest(
            problem = self.writer.convert(problem),
            resolution_mode = ge_pb2.PlanRequest.Mode.Value(guarantee_name)
        )
        self.logger.info(f"Sending PlanOneshot Request: {problem.name}")
        return plan_request

    def consumePlanOneShot(self, request, context):
        res = self.reader.convert(request, self._oneshot_problem)
        assert isinstance(res, PlanGenerationResult)
        self._oneshot_results.put(res)

        self.logger.info(f"Received PlanOneshot result: {res}")

        dummy = ge_pb2.Empty()
        return dummy

    def producePlanAnytime(self, request, context):
        # Wait on the queue, populated by the self.get_solutions method
        problem, guarantee = self._anytime_problems.get(block=True)
        plan_request = ge_pb2.PlanRequest(
            problem = self.writer.convert(problem),
            resolution_mode = ge_pb2.PlanRequest.Mode.Value(guarantee.name)
        )
        self.logger.info(f"Sending PlanAnytime Request: {problem.name}")
        return plan_request

    def _anytime_iterator(self, request_iterator, problem: Problem, anytime_stop: Queue) -> Iterator[PlanGenerationResult]:
        try:
            for request in request_iterator:
                res = self.reader.convert(request, problem)
                assert isinstance(res, PlanGenerationResult)
                self.logger.info(f"Received PlanAnytime result for problem {problem.name}: {res}")
                yield res
                if res.status != PlanGenerationResultStatus.INTERMEDIATE:
                    break
        finally:
            # At the end notify the consumePlanAnytime that it can return
            anytime_stop.put(None)

    def consumePlanAnytime(self, request_iterator, context):
        # Create the Iterator to put in the queue
        wait_termination_queue = self._anytime_stop
        res_iterator = self._anytime_iterator(request_iterator, self._anytime_problem, wait_termination_queue)
        self._anytime_results.put(res_iterator)

        self.logger.info(f"Received PlanAnytime generator")

        # Wait that the user stops using the iterator
        wait_termination_queue.get(block=True)

        dummy = ge_pb2.Empty()
        return dummy

    def produceValidatePlan(self, request, context):
        # Wait on the queue, populated by the self.validate method
        problem, plan = self._validate_problems.get(block=True)
        validation_request = ge_pb2.ValidationRequest(
            problem = self.writer.convert(problem),
            plan = self.writer.convert(plan)
        )
        self.logger.info(f"Sending ValidatePlan Request: {problem.name}\n  {plan}")
        return validation_request

    def consumeValidatePlan(self, request, context):
        res = self.reader.convert(request)
        assert isinstance(res, ValidationResult)
        self._validate_results.put(res)

        self.logger.info(f"Received ValidatePlan result: {res}")

        dummy = ge_pb2.Empty()
        return dummy

    def produceCompile(self, request, context):
        # Wait on the queue, populated by the self.compile method
        problem, compilation_kind = self._compile_problems.get(block=True)
        self.logger.info(f"Sending Compile Request: {problem.name}")
        return self.writer.convert(problem)

    def consumeCompile(self, request, context):
        res = self.reader.convert(request, self._compile_problem)
        assert isinstance(res, CompilerResult)
        self._compile_results.put(res)

        self.logger.info(f"Received Compile result: {res}")

        dummy = ge_pb2.Empty()
        return dummy

    def wait_for_termination(self):
        self.server.wait_for_termination()

def _normalize_optimality_guarantee(problem: Problem, optimality_guarantee: Optional[Union[OptimalityGuarantee, str]]) -> OptimalityGuarantee:
    if optimality_guarantee is None:
        if problem.quality_metrics:
            optimality_guarantee = OptimalityGuarantee.SOLVED_OPTIMALLY
        else:
            optimality_guarantee = OptimalityGuarantee.SATISFICING
    elif isinstance(optimality_guarantee, str):
        try:
            optimality_guarantee = OptimalityGuarantee[optimality_guarantee.upper()]
        except KeyError:
            raise UPUsageError(
                f"{optimality_guarantee} is not a valid OptimalityGuarantee."
            )
    else:
        assert isinstance(optimality_guarantee, OptimalityGuarantee), "Typing not respected"
    assert isinstance(optimality_guarantee, OptimalityGuarantee)
    return optimality_guarantee

def _normalize_compilation_kind(compilation_kind: Union[OptimalityGuarantee, str]) -> OptimalityGuarantee:
    if isinstance(compilation_kind, str):
        try:
            compilation_kind = CompilationKind[compilation_kind.upper()]
        except KeyError:
            raise UPUsageError(
                f"{compilation_kind} is not a valid CompilationKind."
            )
    else:
        assert isinstance(compilation_kind, CompilationKind), "Typing not respected"
    assert isinstance(compilation_kind, CompilationKind)
    return compilation_kind
