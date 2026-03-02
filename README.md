# Hot reloaded code replay engine

Do you like the prototyping pace of Jupyter notebooks? Do you wish you could have the
same experience in your full code base, not just for a notebook? Are you infuriated by
having to re-run your boot-up heavy program with slow data loading just so you can hit a
breakpoint and debug?

Fever is here for you! Without changing a single line of code in your code base, fever
lets you:

- Interactively re-run code traces from one arbitrary function to another, while keeping
  the state of your program warm in memory.
- Hot reload code changes anywhere in your code base, so you can iterate aggressively on
  the *hot parts of your code* and see the output instantly, without going through the
    *slow, cold parts of your code*.
- Drop in a debugger automatically when your code trace finishes, or on exceptions
thrown, letting you investigate bugs and fix them by reviving your program instantly.

![fever](https://github.com/user-attachments/assets/d181ae46-82eb-4581-b01d-0decea58a9b7)


<div align="center">
<a href="https://asciinema.org/a/806651"  target="_blank" style="display: inline-block;"><i>Link to the asciinema</i></a>
</div>
<br>

### Feeling feverish? Give it a try!

`uv pip install fever`

- Hot reload when a file changes on disk: `uv run fever watch <my_python_code.py> <my_arg1> <--my-arg-2=val> <...>`
- Interactive code replay TUI: `uv run fever replay <my_python_code.py> <my_arg1> <--my-arg-2=val> <...>`


**Fever is currently under heavy development and is still at the prototyping stage. We
are working hard on bringing the robustness to the best standards.**


# How does it work?

Fever is at its core a hot code reloading engine, but on steroids. Hot reloading is
proactive: fever analyzes your modules upon import and wraps functions to re-route
calls to the latest compiled version. Here's the gist:

### 1. Import hooks and AST analysis

We first implement an [import hook](https://docs.python.org/3.14/reference/import.html#import-hooks)
so that we can record module imports (and optionally a dependency graph). Then we build
an AST of the code so that we can analyze all callables and keep track of: module-level
functions, class methods, lambdas (well that's probably not gonna happen), etc.

### 2. Wrapping callables

Once we found all the callables in a module, we can wrap them in a proxy upon import,
before returning the code to the user. With this mechanism in place, we are able to
track which callable was changed on disk -- ie hash all callables in the dependency
graph of the module and detect hash changes. Up to this point, everything that happened
is fully transparent to the user.


### 3. Hot code reloading

Whenever the user calls for a reload, each changed callable is reloaded, and only that,
and re-executed in the registry's isolated namespace. Thanks to the proxy wrapper, every
place where a function was previously imported and called will automatically call the
new code. Pretty sweet, right?


# How does it differ from Jurigged, Lemonade, reloadium and others?

1. More advanced hot reloading mechanism:
    a. Instead of compiling the entire module to replace just one function in the
    registry, we compile that one function individually, saving unnecessary compute
    which can make a difference for larger modules.
    b. Handles new function, class, method definitions (even without recompiling the entire
    module).
2. Smart caching of function calls for instant hot reloading:
    a. Only reload the code that was changed on disk.
    b. Only re-execute the code that was reloaded (reuse from cache for other
    functions).
    c. (TODO) Handle loops in a smart way! Aggregate results when possible.
3. Live code replay à la Jupyter:
    a. Record program trace and allow selecting start and end nodes for replay.
    b. Allow to hang on exception or at the end of the trace subgraph.
    c. (TODO) Process-independent function execution for deterministic and mutation-free
    trace replay.
4. (TODO) Handle multiprocessing for PyTorch dataloaders.
5. (TODO) Handling GPU computation? (no idea what/how/why yet).
6. (TODO) Keep a history of changes so that we can revert code changes (e.g. in case the new
    code causes a crash).


# Roadmap

- [x] v0.0.1: Basic proof of concept for hot code reloading only callables that changed
  on disk
- [x] v0.0.2: Demonstrate the PoC on one of my complex projects (matchbox)
- [x] v0.0.3: Implement a reliable and unit-tested import hook mechanism
- [x] v0.0.4: Implement a reliable and unit-tested hot reloading mechanism
- [x] v0.0.5: Add interface to file watcher to trigger reload events
- [x] v0.0.6: Implement a reliable (and unit-tested) smart caching mechanism
- [x] v0.0.7: Add a tool executable to wrap a script and launch the trace replay TUI
- [ ] v0.0.8: PDB++ TUI integration + flexible API
- [ ] v0.0.9: Live trace graph update for the TUI
- [ ] v0.1.0: Rewrite the architecture into a "process isolation" replay engine with
    IPC: "A process-isolated execution engine that boots into a pre-patched runtime and then
    accepts replay commands over IPC."
- [ ] v0.1.1: Handle all edge cases (decorated functions, methods, etc.) in hot reloading engine
