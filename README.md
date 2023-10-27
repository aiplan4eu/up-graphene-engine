# up-graphene-engine
This repository stores the code to easily connect a new component being created to the unified-planner component in the ai4experiments graphene platform.

This repository aims to simplify and streamline the integration of a new use-case on the [AI4Experiments platfrom](https://aiexp-dev.ai4europe.eu/#/home). At the moment we are using the DEV version of the platform because the original version does not support recursively defined proto files.

## Step by step slides guide
[Here](https://docs.google.com/presentation/d/1v1R6OdxgOXRrMl8kgfoBc9Ug8xVnPpqz1BUVw3mskwo/edit#slide=id.p) you can find the set of slides that guides you in the step-by-step integration of a component in the platform, using the up-graphene-engine.


## Introduction

The platform needs basically 2 things:

1. A protobuf file, that defines the interface of the chosen GRPC server
2. A docker image that launches a GRPC server on the port 8061 and, if needed, a GUI on the port 8062.

## Steps
### 1: Create and copy starting files for the docker folder

In the demo of [TSB-Space](https://github.com/aiplan4eu/ai4experiments-tsb-space) you can see an example of a working intergation.
The starting docker files can be copy-pasted from there:

* config.json -> Simple copy-paste.
* docker-compose.yml -> If a GUI is not needed, the last row (- "8003:8062") can be deleted.
* requirements.txt -> Those are the basic requirements; if your use-case has more python requirements, they can be added here.
* Dockerfile -> This file needs some modifications, but the file in TSB-Space is a starting point to show at least what NEEDS to be done. During the step-by-step guide, when a line of this file becomes relevant, there will be a note.

### 2: Copy this repository inside the docker folder

This can be done both by using git clone command:

```git clone https://github.com/aiplan4eu/up-graphene-engine.git```

Or by adding it as a submodule (as in the TSB-Space demo)

```git submodule add https://github.com/aiplan4eu/up-graphene-engine.git```

After this is done, in the demo Dockerfile the command ```RUN pip install /up-service/up-graphene-engine``` makes sense, where the up-graphene-engine is installed as a python module; and indeed, in the code it will used as a python module.

### 3: How to use the up-graphene-engine python package in your code

Once installed (with the docker command above), the up-graphene-engine package is really easy to use, the architecture resembles an Engine of the unified_planning that implements all the relevant methods of the supported Operation Modes.

Currently:
| **Operation Mode** | **Relevant method** |
|--------------------|---------------------|
| OneshotPlanner     | solve               |
| AnytimePlanner     | get_solutions       |
| Compiler           | compile             |
| PlanValidator      | validate            |

The following code shows the steps:
```python
from up_graphene_engine.engine import GrapheneEngine
engine = GrapheneEngine(port=8061) # 8061 is also the default port, so it can be omitted
res = engine.solve(problem, "solved_optimally")
```

The `solve` method interacts with the unified-planner component trough GRPC and `res` is the [PlanGenerationResult](https://unified-planning.readthedocs.io/en/latest/api/engines/PlanGenerationResult.html) returned.

How the `GrapheneEngine` is used depends a lot on the specific use-case.

Also, in this part the user might interact with the GUI. What the GUI does it's very use-case specific, for example in the TSB-Space the user decides which activities and in which order must be performed by the rover.

### 4: The .proto file

The .proto file is already ready and it's the one that you can find in `up-graphene-engine/up_graphene_engine/grpc_io/graphene_engine.proto`

### 5: Onboarding the model in the platform and creating the solution

This part is divided in substeps:

1. Create an account on the [AI4Experiments platfrom](https://aiexp-dev.ai4europe.eu/#/home) and log in.
2. Click on `ON-BOARDING MODEL`, on the left side.
3. Choose a name for the model
4. Insert the URI where the docker image is stored (for example, the TSB-Space docker image is stored [here](https://hub.docker.com/layers/frambaluca/ai4eu-experiments/tsb-space-v3/images/sha256-8a1b4fdee11092795e707f53de36049790251f76eb831502f9a03c5ec65fd97c?context=repo) and the URI is `docker.io/frambaluca/ai4eu-experiments:tsb-space-v3`)
5. Browse for the protobuf file. The correct file is the one in the `up-graphene-engine/up_graphene_engine/grpc_io/graphene_engine.proto` path.
6. After the step above, go in `MY MODELS`, on the left side. There you will find a model with the name you chose; click on that model.
7. After a short loading, the button `Manage My Model` (on the upper side) becomes clickable; click it to get into the model options.
8. From there click on `Manage Publisher/Authors` and insert a publisher name and at least one author.
9. Go on the `Publish to Marketplace` section (below `Manage Publisher/Authors`), scroll down to `Model Category` (section 4), click on `Model Category` to modify it and select `Data Transformer`, `Scikit-Learn` and update. After completing this step the component will show up in the design studio.
10. Go in the `DESIGN STUDIO` (on the left side), and search in `Data Transform Tools` for your component and drag-and-drop it to the center; do the same thing with the `unified-planning-server` component.
11. Now it's the "wiring" part, where the input and output of components must be connected one-another. Every component has some circles around; those represent inputs and outputs; white background represents input, black background of the circle represents output. For every operation mode used by your components (in the TSB-Space example only `planOneShot` is used) both input and output of the `unified-planning-server` `planOneShot` must be connected to your component.<br /><br />
In particular:

    * The input of the `planOneShot` method must be connected to the output of the method `producePlanOneShot` in your component.
    * The output of the `planOneShot` method must be connected to the input of the method `consumePlanOneShot` in your component.

12. After all the wiring is done, the solution can be `saved` and `validated` (on the upper-right).

### 6: Deploying and using the solution

After the solution is correctly validated, it is possible to deploy and execute it; this is done in `Deploy for Execution` -> `Preprod Playground`.<br />
By clicking on `Preprod Playground` a new page will open; when all status checks are green and the status is `Ready`, the different docker containers are ready to use.
Click `Run` to start the orchestrator.

If your component has a GUI, it can be opened under the `WebUI/Folder` sign.

If everything is implemented correctly, now you can use your GUI and get the expected result.
