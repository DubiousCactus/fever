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

2. AST analysis

Visitor pattern with the `ast` module.

3. Hot code reloading

?
