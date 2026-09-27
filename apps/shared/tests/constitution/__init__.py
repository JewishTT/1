"""Constitutional tests: the invariants that outlive any feature.

Feature 019, T037. Every other test in this repository tests *a* behaviour of *a* module,
and is entitled to change when that module is rewritten. These test the things the platform
promised itself before any feature existed, and a change to one of them is not a refactor -
it is the platform deciding to be something else.

That is why they are in their own package with no imports from any feature's code path. A
constitutional test that had to import a feature's helper to build its fixture would stop
being able to fail when that helper changed, which is the only failure mode a constitutional
test cannot have.

**Each file here names the invariant it defends in its module docstring, and each test
class names the failure it expects.** T038's requirement is that every one of these can
fail: a test that cannot fail is not a test, and for a constitutional test that is worse
than useless, because it would be quoted as evidence of a guarantee nobody is keeping.
"""
