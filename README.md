````markdown
# CompilerMate

A compiler's diagnostic is usually the last thing it says to you. It parses your code, finds a problem, prints a message, and leaves you to decide what to do next. Whatever richer picture it had, such as which token it expected, where exactly things went wrong, and what the grammar required at that point, is no longer directly available through the interaction. You are left to reconstruct it yourself: read the error, figure out what it means, fix the file, recompile, and hope you got it right.

CompilerMate started with a question I kept coming back to: what if the diagnostic didn't have to be the end of the interaction? What if the compiler's understanding of the failure stayed around long enough for you to actually ask it something?

That's the experiment. Not a replacement compiler or a new language, but a small, honest test of whether a compiler's diagnostic state can be kept addressable instead of disposable, and what a session built around that looks like when it's real code rather than a slide.

## The observation

When a compiler hits an error, it already knows a lot more than the one-line message it shows you: the tokens it read, exactly where parsing broke down, what it expected next, what it found instead, and the grammar rule that was violated. Modern tooling, including LSPs, quick fixes, and inline diagnostics, already surfaces a good amount of this. I'm not claiming otherwise, and I'm not trying to rebuild any of it.

What caught my attention was narrower: after that diagnostic is produced, the conversation about it usually stops. You get the message, and any further exploration, such as "why exactly?", "what are my options?", or "just fix it", has to be reconstructed by you from scratch. The compiler has not necessarily exposed the context in a form that lets you keep asking questions about the same failure.

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

## What the MVP actually does

The current implementation is deliberately tiny. It's a hand-written lexer and parser for a single kind of statement, an `int` declaration, built specifically so I could get one real diagnostic all the way through a full interaction cycle rather than half-implementing a dozen.

The one case it handles:

```text
int x = 10
```

The parser notices the missing `;`. That failure becomes a structured `Diagnostic` object containing the phase, type, line, column, what was expected, and what was actually found. A `Session` holds onto it. From there you can drive the interaction:

```text
COMPILER: Error at line 1, column 11: expected ";"
YOU: > explain
COMPILER: Expected ';' after expression (expected ';', got 'EOF') at line 1, column 11.
YOU: > suggest fixes
COMPILER: [1] Insert missing semicolon at line 1, column 11.
YOU: > apply 1
COMPILER: Fix applied. Recompiling...
COMPILER: Compilation successful.
```

`explain` and `suggest fixes` both read from the same retained diagnostic. They are two different views on one piece of state, not two independent lookups. `apply 1` is where it gets more interesting: applying the repair isn't treated as proof that anything worked. The source is edited, and then the corrected text is run back through the actual lexer and parser. "Compilation successful" only appears once that real recompilation genuinely passes. It isn't a hardcoded response to `apply 1`.

This is the current, complete scope. There's no semantic analysis, no type checking, no symbol table, no IR, no execution, and no general-purpose repair. There is one diagnostic kind, one deterministic fix, and a real end-to-end loop around it.

## Architecture

```text
Source
   ↓
Lexer
   ↓
Parser
   ↓
Diagnostic
   ↓
Session State
   ↓
Interaction (explain / suggest fixes / apply)
   ↓
Repair
   ↓
Source Modification
   ↓
Recompilation
   ↓
Success
```

The distinction that matters here isn't lexing versus parsing. It's the gap between generating a diagnostic and retaining it. A conventional pipeline does the former and exposes the result through a diagnostic message. CompilerMate does the former and then keeps the diagnostic object around, so `explain`, `suggest fixes`, and `apply` all resolve against the same retained state instead of each re-deriving an answer from scratch. Only when a repair is applied does the pipeline get invoked again, from the top, on the corrected source. Nothing is patched in place or assumed to work.

### Modules

* **`lexer.py`**: hand-written lexer producing `int`, identifier, `=`, integer literal, and `;` tokens.
* **`parser.py`**: a small recursive-descent parser for one declaration form. On success it returns a `DeclarationAST`; on failure it builds a `Diagnostic` instead of just raising.
* **`diagnostics.py`**: the `Diagnostic` dataclass containing phase, type, line, column, expected/actual, and message.
* **`repair.py`**: the `Repair` dataclass describing a single deterministic edit, including what to insert and where.
* **`session.py`**: `Session` holds the source, tokens, AST, active diagnostic, and repair candidates. `compile()` runs the pipeline and derives repair candidates from the resulting diagnostic. `apply_repair()` performs the edit and recompiles.
* **`interaction.py`**: the REPL maps the core commands `explain`, `suggest fixes`, and `apply <n>` onto the session, with basic utility commands such as `state`, `help`, and `quit`.
* **`main.py`**: entry point. It reads one line of source, runs the first compile, and drops into the REPL if there's a diagnostic to talk about.

## Why it's built this way

**Python.** Nothing about the experiment needed a systems language, and Python keeps the internal structures, including tokens, the AST node, and the diagnostic object, easy to inspect while building. That mattered because the whole point was to make internal compiler state visible and interactable.

**Hand-written lexer and parser, not a generated one.** A parser generator would have hidden exactly the moment I cared about: where a failure becomes structured data. Writing the parser by hand means I control precisely what gets captured when a rule doesn't match, which is what makes a structured diagnostic possible in the first place.

**A dataclass for `Diagnostic`, not an exception or a string.** Exceptions are useful for control flow. Strings are difficult to query later. A diagnostic that's meant to be queried needs to be a real object with fields something else can read back from. That's the premise the interaction layer depends on.

**CLI, not an editor plugin or GUI.** The thing under test is the interaction model, not a UI. A prompt loop is the smallest possible surface that still lets the loop of explain, suggest, apply, and recompile happen for real.

**Recompilation is mandatory, not implied.** `apply_repair` doesn't just splice the string and declare victory. It calls `compile()` again and reports success only if the second pass actually completes. String editing without re-verifying isn't a repair. It's a guess that looks like one.

## Running it

From the `MVP/` directory:

```bash
python -m compilermate.main
```

It prompts once for a line of source. Try the case it's built for:

```text
SOURCE > int x = 10
```

Then drive the session with `explain`, `suggest fixes`, and `apply 1`.

`demo_input.txt` contains a scripted version of this same sequence if you'd rather pipe it in:

```bash
python -m compilermate.main < demo_input.txt
```

### Tests

```bash
python -m unittest discover -s tests -v
```

The tests cover the lexer's token stream, the parser's success and missing-semicolon paths, the `Diagnostic` and `Repair` dataclasses, and a full integration test that runs the missing-semicolon scenario end to end, including the recompiled source and the resulting AST values.

## Project structure

```text
CompilerMate/
├── MVP/
│   ├── compilermate/
│   │   ├── lexer.py
│   │   ├── tokens.py
│   │   ├── parser.py
│   │   ├── ast.py
│   │   ├── diagnostics.py
│   │   ├── repair.py
│   │   ├── session.py
│   │   ├── interaction.py
│   │   └── main.py
│   ├── tests/
│   └── demo_input.txt
├── Reports for submission/
└── .gitignore
```

The `MVP/` name is literal, not incidental. This is a first milestone, and I expect the layout to grow past it rather than get restructured around it. `Reports for submission/` holds documentation written for one stage of this project's development. It was first built out as coursework, but that is a record of the project's context, not what defines the project.

## Limitations

* One language construct (`int x = value;`), one diagnostic kind (missing `;`), and one repair.
* No semantic analysis. Nothing here knows what a variable means, only whether the syntax is well-formed.
* No symbol table, no IR, and no execution. The AST exists only because the parser needs somewhere to put a successful result.
* The interaction vocabulary is small and deliberately bounded. There is no free-form querying, and there isn't meant to be. Every response comes from structured fields on the diagnostic rather than generated text.
* Recompilation only re-runs lexing and parsing, not any later phase, since none of those phases exist yet.

None of this is a bug list. It's the deliberate size of a first vertical slice, kept small on purpose so the interaction loop could actually be finished and run rather than partially sketched across a bigger pipeline.

## Where this could go

The uninteresting version of "what's next" is just adding more compiler features: more statement types, more diagnostic kinds, a symbol table, semantic checks. That's real work, but it's not the part I find interesting.

The actual open question is what happens to the interaction once the compiler state behind it gets richer. Right now there's exactly one thing to `explain` and exactly one thing to `apply`. What does `explain` look like once there are multiple plausible causes for a type error? What does `suggest fixes` mean once repairs aren't all a single deterministic insertion? Does retained session state stay useful once a program has scope, and the diagnostic needs to reference a symbol table instead of just a token?

Concretely, that could mean more of the existing grammar, such as conditionals, loops, and more types, along with semantic analysis and a real symbol table, more diagnostic kinds with their own bounded repairs, and commands like `why` or `show symbols` that only make sense once there is semantic state to show. None of that is built yet, and I'd rather list it here honestly than have the code imply otherwise.

```
```
