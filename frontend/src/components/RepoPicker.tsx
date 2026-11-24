import { useState } from "react";
import type { ProductApi } from "../api/productApi";
import { useRequest } from "../hooks/useRequest";
import { ErrorNotice } from "./ErrorNotice";

export function RepoPicker({
  api,
  selected,
  onSelect,
}: {
  api: ProductApi;
  selected: string | null;
  onSelect: (repoId: string | null) => void;
}) {
  const [attempt, setAttempt] = useState(0);
  const repos = useRequest(() => api.listRepos(), "repos", attempt);

  if (repos.status === "loading" || repos.status === "idle") {
    return <p>Loading repositories…</p>;
  }
  if (repos.status === "error") {
    return (
      <ErrorNotice
        error={repos.error}
        onRetry={() => setAttempt((n) => n + 1)}
      />
    );
  }
  if (repos.data.repos.length === 0) {
    return <p>No indexed repositories are available.</p>;
  }
  return (
    <label>
      Repository{" "}
      <select
        value={selected ?? ""}
        onChange={(e) => onSelect(e.target.value || null)}
      >
        <option value="">Select a repository…</option>
        {repos.data.repos.map((repo) => (
          <option key={repo.repo_id} value={repo.repo_id}>
            {repo.display_name} ({repo.file_count} files)
          </option>
        ))}
      </select>
    </label>
  );
}
