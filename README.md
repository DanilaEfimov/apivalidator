# apivalidator

Course project for the Web Development discipline. An API request validator with a simple DSL for describing rules. The assignment has been reviewed and approved by @RuMarS.

The tool lets you describe validation rules for an incoming API request in a small domain-specific language, then apply those rules to the request and get a validation result. The DSL is built around logical expressions over request fields (`method`, `path`, `query.*`, `body.*`), with comparisons, `in` / `matches` / `starts_with` operators, function calls, and `and` / `or` / `not` logic. Parsing is done with [Lark](https://github.com/lark-parser/lark) using an EBNF grammar.
