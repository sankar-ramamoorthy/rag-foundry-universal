# Feature Specification: [FEATURE NAME]

**Feature Branch**: `[###-feature-name]`

**Created**: [DATE]

**Status**: Draft

**Tracking Issue**: #[ISSUE_NUMBER]

**Roadmap Context**: [Phase / WP if applicable]

**Input**: User description: "$ARGUMENTS"

## Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: Scenarios should be PRIORITIZED and ordered by importance.
  Each scenario must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.

  Not every feature has a conventional end user. A scenario may be:
  - a user journey, for product-facing functionality
  - an operator/developer scenario, for infrastructure or tooling work
  - an evaluation scenario, for quality/evaluation work (e.g. "establish a
    baseline," "distinguish failure classes," "produce an evidence-backed
    decision") — do NOT force a fake "As a user, I want..." framing onto work
    that has no end user; describe what is being measured or decided instead.

  Assign priorities (P1, P2, P3, etc.) to each scenario, where P1 is the most critical.
  Think of each scenario as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated (to users, or via evaluation evidence) independently
-->

### User Story 1 - [Brief Title] (Priority: P1)

[Describe this user journey in plain language]

**Why this priority**: [Explain the value and why it has this priority level]

**Independent Test**: [Describe how this can be tested independently - e.g., "Can be fully tested by [specific action] and delivers [specific value]"]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]
2. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

### User Story 2 - [Brief Title] (Priority: P2)

[Describe this user journey in plain language]

**Why this priority**: [Explain the value and why it has this priority level]

**Independent Test**: [Describe how this can be tested independently]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

### User Story 3 - [Brief Title] (Priority: P3)

[Describe this user journey in plain language]

**Why this priority**: [Explain the value and why it has this priority level]

**Independent Test**: [Describe how this can be tested independently]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

[Add more user stories as needed, each with an assigned priority]

### Edge Cases

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right edge cases.
-->

- What happens when [boundary condition]?
- How does system handle [error scenario]?

## Non-Goals

<!--
  ACTION REQUIRED: Explicitly list what this feature does NOT do or decide.
  This matters most for investigative/evaluation work, where it's tempting to
  presuppose an outcome (e.g. "add a reranker") that the feature is actually
  meant to determine. Remove only if genuinely nothing is worth excluding.
-->

- [Explicitly excluded behavior or work]

## Governing References

<!--
  List only documents that constrain this feature.
  Reference them; do not restate their rules here (Constitution Principle VII).
  If this spec appears to conflict with an ADR, surface the conflict explicitly
  rather than resolving it silently in either direction.
-->

- Constitution: `.specify/memory/constitution.md`
- ADRs: [applicable ADR references]
- Audit/roadmap: [applicable references]
- Tracking issue: #[ISSUE_NUMBER]

**Known conflicts**: None / [describe explicitly]

## Requirements *(mandatory)*

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right functional requirements.
-->

### Functional Requirements

- **FR-001**: System MUST [specific capability, e.g., "allow users to create accounts"]
- **FR-002**: System MUST [specific capability, e.g., "validate email addresses"]
- **FR-003**: Users MUST be able to [key interaction, e.g., "reset their password"]
- **FR-004**: System MUST [data requirement, e.g., "persist user preferences"]
- **FR-005**: System MUST [behavior, e.g., "log all security events"]

*Example of marking unclear requirements:*

- **FR-006**: System MUST authenticate users via [NEEDS CLARIFICATION: auth method not specified - email/password, SSO, OAuth?]
- **FR-007**: System MUST retain user data for [NEEDS CLARIFICATION: retention period not specified]

### Key Entities *(include if feature involves data)*

- **[Entity 1]**: [What it represents, key attributes without implementation]
- **[Entity 2]**: [What it represents, relationships to other entities]

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: [Measurable metric, e.g., "Users can complete account creation in under 2 minutes"]
- **SC-002**: [Measurable metric, e.g., "System handles 1000 concurrent users without degradation"]
- **SC-003**: [User satisfaction metric, e.g., "90% of users successfully complete primary task on first attempt"]
- **SC-004**: [Business metric, e.g., "Reduce support tickets related to [X] by 50%"]

## Evaluation Evidence

<!--
  MANDATORY for quality-sensitive retrieval, ranking, generation, chunking,
  embedding, or prompt/context-assembly work under Constitution Principles III
  and VIII. Remove only when genuinely not applicable and state why.
-->

**Evaluation Required**: Yes / No

**Baseline**:
- [Existing behavior or metric being compared]

**Metrics**:
- [Metric and how it is measured]

**Decision Criteria**:
- [What result justifies or rejects a proposed follow-up]

**Evidence Artifact**:
- [Where results will be recorded]

## Assumptions

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right assumptions based on reasonable defaults
  chosen when the feature description did not specify certain details.
-->

- [Assumption about target users, e.g., "Users have stable internet connectivity"]
- [Assumption about scope boundaries, e.g., "Mobile support is out of scope for v1"]
- [Assumption about data/environment, e.g., "Existing authentication system will be reused"]
- [Dependency on existing system/service, e.g., "Requires access to the existing user profile API"]
