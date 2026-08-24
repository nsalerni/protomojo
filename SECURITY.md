# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately through
[protomojo security advisories](https://github.com/nsalerni/protomojo/security/advisories/new).
Do not include vulnerability details in a public issue. You should receive an
initial response within one week.

## Scope

protomojo parses untrusted Protocol Buffers binary data and generates Mojo code
for proto3 schemas. The decoder rejects malformed wire data and applies the
protobuf reference nesting-depth limit. The
[compliance report](COMPLIANCE.md) records the current reference tests.

JSON mapping, proto2 semantics, Editions, and text format are
outside the current supported scope. The project has not had an external
security review.
