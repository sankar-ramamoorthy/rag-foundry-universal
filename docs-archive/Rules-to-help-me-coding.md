Test-Guided Development (TGD)
Every issue must define what will be tested before coding begins,
but the test may be written before or immediately after the first implementation spike.

For each issue:

Write acceptance criteria
Write 1–2 skeletal tests (even if they fail trivially)
Implement the minimum code
Expand tests only as confidence grows

Acceptance criteria should describe observable behavior, not implementation.

Standard Acceptance Criteria Template

Add this to every issue:

### Acceptance Criteria
- [ ] API endpoint exists and responds successfully
- [ ] Behavior is observable via HTTP or database state
- [ ] At least one automated test validates the behavior
- [ ] No breaking changes to existing contracts
