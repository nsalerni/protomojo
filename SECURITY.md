# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately through
[protomojo security advisories](https://github.com/nsalerni/protomojo/security/advisories/new).
Do not include vulnerability details in a public issue. You should receive an
initial response within one week.

## Scope

protomojo parses untrusted Protocol Buffers binary data and proto3 JSON, then
generates Mojo code for proto3 schemas. The binary decoder rejects malformed
input and applies the protobuf reference nesting-depth limit. The JSON decoder
rejects malformed input and bounds nesting while skipping ignored unknown
values. The
[compliance report](COMPLIANCE.md) records the current reference tests.

JSON input is supported only for generated messages made entirely of singular
primitive fields. Structured messages, enums, well-known types, proto2
semantics, Editions, and text format are outside the current supported scope.
The project has not had an external security review.
