# Tasks: production correctness programme

Tracking issues: #160, #161, #166-#171
Spec: [spec.md](./spec.md); plan: [plan.md](./plan.md)
Per-issue plans/acceptance/tasks: [issues](./issues/)

- [x] P001 Verify GitHub access and existing #160/#161/#144/#91/#164 state.
- [x] P002 Create issues #166-#171 with problem, plan and acceptance gates.
- [x] P003 Amend 004 spec/plan/tasks for audit M1-M8, including no-resume scope.
- [x] P004 Link roadmap, status, KB indices and historical audit to programme.
- [x] P005 Validate docs/probes; commit/push amended #164; merge passing CI.
- [ ] R001 Implement/test WP-R1 #160; commit/push/merge separate PR.
- [ ] R002 Implement/test WP-R2 #161; commit/push/merge separate PR.
- [ ] R003 Implement/test WP-R3 #166; include #144 serving state; separate PR.
- [ ] R004 Implement/test WP-R5 #168 snapshot/cache contract; separate PR.
- [ ] R005 Implement/test/evaluate WP-R4 #167 evidence delivery; separate PR.
- [x] R006 Implement/test WP-R6 #169 health/provenance; PR #172 merged.
      Target-host Docker health/provenance validation remains in R010.
- [ ] R007 Implement/test WP-R7 #170 bounded blocking-I/O isolation; separate PR.
- [ ] R008 Run #160 pinned Linux memory gates and #161 kill/recovery gates.
- [ ] R009 Run #167 pinned clean retrieval/generation quality gates.
- [ ] R010 Verify #171 current Linux lifecycle/image/health/UI/migration/redeploy;
      write truthful release record and merge tooling/evidence PR.
- [ ] R011 Audit every issue's acceptance evidence; close only satisfied issues,
      update status/roadmap/KB links and verify all requested merges remotely.
- [ ] R012 Diagnose/fix #176 post-delete ANN recall; separate PR and measured
      regression per [follow-up](./issues/post-delete-ann.md). Include in R010/R011.

For EACH R001-R010: update issue-specific acceptance checklist, exact test
results, PR link, current status and HANDOFF. Preserve outstanding gates.
Do not mark a box complete based on planned tests, mocked integration or
historical production evidence from another revision.
