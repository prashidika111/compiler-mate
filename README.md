````markdown
# CompilerMate

A compiler's diagnostic is usually the last thing it says to you. It parses your code, finds a problem, prints a message, and leaves you to decide what to do next. Whatever richer picture it had, such as which token it expected, where exactly things went wrong, and what the grammar required at that point, is no longer directly available through the interaction. You are left to reconstruct it yourself: read the error, figure out what it means, fix the file, recompile, and hope you got it right. CompilerMate started with a question I kept coming back to: what if the diagnostic didn't have to be the end of the interaction? What if the compiler's understanding of the failure stayed around long enough for you to actually ask it something?
That's the experiment. Not a replacement compiler or a new language, but a small, honest test of whether a compiler's diagnostic state can be kept addressable instead of disposable, and what a session built around that looks like when it's real code rather than a slide.

## The observation

When a compiler hits an error, it already knows a lot more than the one-line message it shows you: the tokens it read, exactly where parsing broke down, what it expected next, what it found instead, and the grammar rule that was violated. Modern tooling, including LSPs, quick fixes, and inline diagnostics, already surfaces a good amount of this. I'm not claiming otherwise, and I'm not trying to rebuild any of it. What caught my attention was narrower: after that diagnostic is produced, the conversation about it usually stops. You get the message, and any further exploration, such as "why exactly?", "what are my options?", or "just fix it", has to be reconstructed by you from scratch. The compiler has not necessarily exposed the context in a form that lets you keep asking questions about the same failure.

## The question

What if the compiler's current diagnostic didn't just get printed and discarded? What if it stayed live as session state, so you could keep interacting with it?
```text
Developer → Compiler → Diagnostic → Developer        (conventional)

Developer
   ↕
Interaction
   ↕
Compiler state                                        (what CompilerMate tries)

````

The compiler pipeline itself isn't made bidirectional. Lexing and parsing still run forward, the way they normally do. What changes is what happens to the result of that pipeline. Instead of collapsing into a printed string, a failure becomes a structured object that a small interaction layer can be asked about.
The way I think about it is simple: the compiler is the experimental environment, and the interaction model is the actual subject of the experiment.
The distinction that matters here isn't lexing versus parsing. It's the gap between generating a diagnostic and retaining it. A conventional pipeline does the former and exposes the result through a diagnostic message. CompilerMate does the former and then keeps the diagnostic object around, so `explain`, `suggest fixes`, and `apply` all resolve against the same retained state instead of each re-deriving an answer from scratch. Only when a repair is applied does the pipeline get invoked again, from the top, on the corrected source. Nothing is patched in place or assumed to work.

## Modules and Architecture

CompilerMate has evolved from an interactive compiler experiment into a code investigation and verification tool integrated with Visual Studio Code in the form of an "extension" I can use locally. While its essence can not be guaranteed in a fast-paced world influenced with AI, I personally think this experiment would be of huge help to someone still trying to learn and understand codes. 

### Python Investigation Engine

The engine is responsible for examining code, producing structured findings, supporting investigations, and handling verification-related operations.
- **`analyzers/`**: Contains focused analysis modules for delimiter mismatches, indentation problems, missing colons, string-related issues, undefined names, and unused imports.
- **`models.py`**: Defines the structured models used to represent investigation information and related data.
- **`investigator.py`**: Coordinates investigation-related operations.
- **`conversation.py`**: Implements the engine's structured investigation and interaction workflow.
- **`verifier.py`**: Handles verification-related logic and records verification outcomes.
- **`cli.py`**: Provides a command-line entry point for interacting with the engine.
- **`__main__.py`**: Allows the engine package to be invoked as a Python module.
The engine also has a dedicated test suite covering the analysis modules, investigation workflow, verification behavior, scenarios, and communication protocol.

### VS Code Extension

The extension brings CompilerMate's investigation workflow into the developer's existing coding environment. It is implemented in TypeScript and communicates with the Python engine.
- **`extension.ts`**: Entry point for the VS Code extension and its editor integration.
- **`engineBridge.ts`**: Coordinates communication between the extension and the Python engine.
- **`investigationStore.ts`**: Manages persisted investigation records and supports reopening previous investigations.
- **`issuesTree.ts`**: Integrates issue information into the VS Code interface.
- **`resultsPanel.ts`**: Presents investigation results to the developer.
- **`quickFixProvider.ts`**: Integrates proposed fixes with VS Code's quick-fix workflow.
- **`verificationEngine.ts`**: Connects verification-related behavior to the extension workflow.
- **`types.ts`**: Defines shared TypeScript types used across extension components.
- **`src/test/`**: Contains extension-side tests, including tests for the engine bridge.
The extension also contains a bundled copy of the Python engine under `extension/engine/`, along with a bundling script and packaging configuration.

### Investigation History and Verification

Two important parts of the current design are investigation persistence and verification.
An investigation should not disappear into an unstructured conversation. CompilerMate retains investigation records and supports reopening previous investigations, with source snapshots and hash information providing context about the code state associated with a record.
Similarly, proposing a fix and verifying it are treated as separate operations. A proposed change is not automatically considered correct simply because it appears plausible. Verification results must be interpreted according to the checks actually performed.

## Why It's Built This Way

**Python for the investigation engine.** Python makes the analysis logic and its internal structures straightforward to develop and inspect. It also provides a practical environment for building focused source-code analyzers and testing their behavior.
**TypeScript for the editor integration.** The VS Code extension provides the interface through which developers interact with CompilerMate. Keeping the editor-facing logic separate from the Python engine gives the project a clearer boundary between the user workflow and the investigation logic.
**Structured findings instead of opaque conclusions.** CompilerMate is intended to distinguish observed evidence from inference and unresolved questions. This matters because a plausible explanation is not necessarily a proven root cause. Structured findings make the investigation easier to inspect and reason about.
**Investigation and verification as separate stages.** Generating a proposed fix and establishing whether it works are different tasks. Keeping verification distinct makes it possible to report what was checked without treating a generated suggestion as proof of correctness.
**Persistent records instead of disposable interactions.** Investigation history makes it possible to return to previous work and examine the information associated with it. This supports traceability beyond a single debugging session.

**A local VS Code extension rather than a globally published product.** The current extension has been developed and exercised locally through VS Code's Extension Development Host. This provides a practical environment for testing the full workflow without requiring a public release. The extension has not been published as a globally available VS Code Marketplace product.

## Running CompilerMate Locally

CompilerMate is currently intended for local development and testing. It is not yet a globally published extension that users can install directly from the VS Code Marketplace.
### Prerequisites
- Visual Studio Code
- Git
- Node.js and npm
- Python, using a version compatible with the project
### 1. Clone the repository
```bash
git clone https://github.com/prashidika111/compiler-mate.git
cd compiler-mate
```
### 2. Open the extension project
```bash
code phase3/extension
```
### 3. Install the extension dependencies
From the extension directory:
```bash
npm install
```
### 4. Compile the extension
```bash
npm run compile
```
### 5. Launch the local development version
1. Open the extension project in VS Code.
2. Open **Run and Debug**.
3. Select the provided extension launch configuration.
4. Press **F5** to launch the Extension Development Host.
5. Open a suitable Python file in the new VS Code window and exercise the available CompilerMate workflow.
The Extension Development Host runs a separate VS Code window with the extension loaded for development. It is a local testing environment, not a global installation or public release.
The repository includes VS Code launch and task configurations to support this workflow.
> **Note:** These instructions describe the local development workflow. They do not imply that CompilerMate has been packaged, published, or tested across all operating systems and environments.

## Tests

CompilerMate includes tests for the Python investigation engine and the TypeScript extension.
### Python engine
From the repository root:
```bash
python -m unittest discover -s phase3/engine/tests
```
### VS Code extension
From `phase3/extension`, inspect the available scripts:
```bash
npm run
```
Run the test script defined in `package.json`. Extension tests may require the VS Code test environment and the relevant development dependencies.
### Manual workflow testing
The extension should also be exercised through the Extension Development Host for better result and assurance. 
1. Open a Python file containing an issue supported by the current analyzers.
2. Start a CompilerMate investigation.
3. Examine the findings and available supporting information.
4. Review a proposed fix before deciding whether to apply it.
5. Inspect the verification outcome.
6. Reopen a previous investigation and inspect its retained information.
These steps exercise the extension as a developer would use it, complementing the automated tests.

## Project Structure

```text
CompilerMate/
├── .vscode/
│   ├── launch.json
│   └── tasks.json
│
├── MVP/
│   └── compilermate/
│       └── ... earlier implementation
│
└── phase3/
    ├── demo_scenarios.py
    ├── TESTING.py
    ├── engine/
    │   ├── compilermate_engine/
    │   │   ├── analyzers/
    │   │   ├── cli.py
    │   │   ├── conversation.py
    │   │   ├── investigator.py
    │   │   ├── models.py
    │   │   └── verifier.py
    │   └── tests/
    │
    └── extension/
        ├── engine/
        │   └── compilermate_engine/
        ├── media/
        ├── scripts/
        ├── src/
        │   ├── engineBridge.ts
        │   ├── extension.ts
        │   ├── investigationStore.ts
        │   ├── issuesTree.ts
        │   ├── quickFixProvider.ts
        │   ├── resultsPanel.ts
        │   ├── types.ts
        │   ├── verificationEngine.ts
        │   └── test/
        ├── package.json
        └── tsconfig.json
```
The latest implementation lives under `phase3/`, which is the final phase for now, where the investigation engine and VS Code extension are maintained as distinct components. The bundled engine under `phase3/extension/engine/` allows the extension to carry its Python engine alongside the editor integration. The standalone engine under `phase3/engine/` remains the development and testing location.

## Limitations

CompilerMate is an evolving investigation and verification tool, not a universal automated debugging system as this was built just as a form of an experiment.
- The current analyzers cover selected categories of Python issues rather than every possible syntax, semantic, or runtime defect.
- A static finding does not necessarily establish the root cause of a failure.
- A diagnosis can be incomplete or incorrect even when it is supported by some evidence.
- Verification outcomes depend on the checks that were actually performed and the conditions under which they ran.
- Passing available checks does not prove that a program is correct for every input or environment.
- Investigation quality depends on the source code and diagnostic information available.
- The extension has been exercised locally but has not been released as a globally available VS Code Marketplace product.
- A local development workflow does not, by itself, establish compatibility across all machines and configurations.
These limitations are central to the design. CompilerMate should make the evidence and verification behind an investigation inspectable rather than imply certainty that the implementation cannot establish.

## Where This Could Go

The next step is not simply to add more analyzers or generate more fixes. Those are useful directions, but the more interesting question is how investigation and verification should behave as the available code context becomes richer. How should a diagnosis present several plausible causes without disguising uncertainty? How should the system compare multiple possible fixes? What evidence is sufficient to say a change improved the situation? How can investigation history remain useful as source code changes between sessions? These questions concern the interaction between investigation, evidence, verification, and developer judgment—not merely the number of issues the tool can recognize.
For now, the project has a working local VS Code workflow and a dedicated engine and extension structure. The next stage is to document the implementation accurately, consolidate the project presentation, and determine what would be required for a reliable public release.
Concretely, that could mean more of the existing grammar, such as conditionals, loops, and more types, along with semantic analysis and a real symbol table, more diagnostic kinds with their own bounded repairs, and commands like `why` or `show symbols` that only make sense once there is semantic state to show. None of that is built yet, and I'd rather list it here honestly than have the code imply otherwise.

```
```
