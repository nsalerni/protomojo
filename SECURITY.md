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
rejects malformed input and bounds nesting.

Proto2 schemas, Editions, and text format are out of scope. The project has
not had an external security review. Current reference results are in
[COMPLIANCE.md](COMPLIANCE.md).
