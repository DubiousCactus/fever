# Proactive hot code reloading engine

My previous attempt was reactive: detect which callable threw an exception, reload that
callable. We had to detect whether it was a class __init__, a class method, a
module-level function or a lambda. This wouldn't scale and I had many holes to patch.

The new approach is proactive: we will hook into the __import__ builtin so that we can
record module dependencies. Then we will build an AST of the code so that we can analyze
all callables and keep track of: module-level functions, class methods, lambdas, etc.
And we can keep track of their context too! 
Finally we need to track which piece of code was changed in the tracked module (using
our wrapper module for a given callable), ie hash all callables in the dependency graph
of the module and detect hash changes. Each changed dependency will be reloaded, and we
can then replace object and function references in the saved context.



## How?

1. Import hooks

Install a middleware between the builtin __import__ and the user code, such that we
intercept each call to import() and register the dependencies.
i.e. in module A, user imports modules B and C --> register (B,C) as deps of A.

2. Call tracking

We can track calls between all the callables in the program *at run time*! This is
achieved by monkey-patching callables with a tracking wrapper, after finding all
callables with AST analysis. We can do this on a per-module basis *during import*, fully
transparent to the user. 

After monkey-patching all callables, we get a call graph that updates in real time :) We
can now keep track of everything we need for careful hot code reloading.

3. Hot code reloading

Several ways of doing this? One way might be to keep a registry of callables, such that
we can easily update their code in the registry and keep their cache there too. Not sure
if that is the most efficient solution though!
Another approach is to directly replace the code by recompiling and replacing the
function pointers. Seems fine honestly, and we can use a registry for the cache only.

I think the first approach is a bit easier to deal with caching. We may need to replace
all callables with proxies though, such that the proxies are the interface to the
registry. This shouldn't be too hard!


But then we'll need some machinery (ie visitor pattern) to walk through the call graph
and update callers that depend on the result of the updated callee.


## How does it differ from Jurigged and others?

1. Smart caching of function calls for instant hot reloading.
    a. Only reload the code that was changed on disk.
    b. Only re-execute the code that was reloaded (reuse from cache for other
    functions).
    c. Handle loops in a smart way! Aggregate results when possible, save to disk, or
    opt in for a given strategy?
2. Handle multiprocessing for PyTorch dataloaders.
3. Have a more flexible API that lets us do more things:
    a. Define the scope of hot reloading for a given "root callable".
    b. Allow to hang on exception.
    c. Allow saving a whole execution graph on disk, letting us replay for debugging
    step by step and rewinding, and letting us hot-reload on a "playthrough" file.
4. Handling GPU computation???? (no idea what/how/why yet).
