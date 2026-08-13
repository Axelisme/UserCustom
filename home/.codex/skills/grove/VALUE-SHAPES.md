# Trace a dynamic value's shape

Use this branch when a Python or JavaScript signature does not declare enough
of a parameter's shape.

1. Locate the function with `grove symbols <root> --name <name>`, then read it
   with `grove source <id>`. Record the parameter and every field or operation
   the function requires.
2. Run `grove callers <name> -d <root>`. Account for every call site relevant to
   the behavior under investigation. Each row names its enclosing definition.
3. For each row, take the leaf name after the final `::` and run
   `grove source <file> <leaf-name>`. If that name is overloaded, select the
   matching file and parent from an exact `symbols` query and use its ID. Trace
   how the argument is constructed, resolving constructors, factories, and
   imported bindings with `grove definition --at <file:line:col>` or another
   exact `symbols` query.
4. Merge constructor assignments with caller-side mutations. Distinguish fields
   present on every relevant path from optional or conflicting fields.

The trace is complete when every claimed field and value kind is grounded in a
construction, mutation, or use, and every relevant caller is either included or
explicitly excluded. In statically typed code, first check whether the signature
already supplies this evidence.
