# Proactive hot code reloading engine

[My previous attempt](https://github.com/DubiousCactus/matchbox?tab=readme-ov-file#3-an-interactive-coding-experience-for-fast-iteration-work-in-progress) was reactive: detect which callable threw an exception, reload that
callable. We had to detect whether it was a class __init__, a class method, a
module-level function or a lambda. This wouldn't scale, and I had many holes to patch.

The new approach is proactive and requires analyzing and monkey-patching the user's code
before the user even gets a hold of it.


## How?

### 1. Import hooks and AST analysis

We first implement an [import hook](https://docs.python.org/3.14/reference/import.html#import-hooks)
so that we can record module imports (and optionally a dependency graph). Then we build
an AST of the code so that we can analyze all callables and keep track of: module-level
functions, class methods, lambdas (well that's probably not gonna happen), etc.

### 2. Monkey-patching and proxy callables

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


## How does it differ from Jurigged, Lemonade, reloadium and others?

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
    c. Handle loops in a smart way! Aggregate results when possible, save to disk, or
    opt in for a given strategy?
3. (TODO) Handle multiprocessing for PyTorch dataloaders.
4. Have a more flexible API that lets us do more things:
    a. Define the scope of hot reloading for a given "root callable".
    b. Allow to hang on exception.
    c. Allow saving a whole execution graph on disk, letting us replay for debugging
    step by step and rewinding, and letting us hot-reload on a "playthrough" file.
5. (TODO) Handling GPU computation???? (no idea what/how/why yet).


## Roadmap

- [x] v0.0.1: Basic proof of concept for hot code reloading only callables that changed
  on disk
- [x] v0.0.2: Demonstrate the PoC on one of my complex projects (matchbox)
- [x] v0.0.3: Implement a reliable and unit-tested import hook mechanism
- [x] v0.0.4: Implement a reliable and unit-tested hot reloading mechanism
- [x] v0.0.5: Add interface to file watcher to trigger reload events
- [ ] v0.0.6: Implement a reliable and Unit-tested smart caching mechanism
- [ ] v0.0.7: Add a tool executable to wrap a script and launch the TUI
- [ ] v0.0.8: PDB++ TUI integration + flexible API
- [ ] v0.0.9: Handle all edge cases (decorated functions, methods, etc.)
- [ ] v0.1.0: Hot code reloading system with smart caching and PDB++ TUI
