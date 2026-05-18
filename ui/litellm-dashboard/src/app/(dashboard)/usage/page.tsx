"use client";

import UsagePageView from "@/components/UsagePage/components/UsagePageView";
import { useOrganizations } from "@/app/(dashboard)/hooks/organizations/useOrganizations";
import { useProjects } from "@/app/(dashboard)/hooks/projects/useProjects";
import useTeams from "@/app/(dashboard)/hooks/useTeams";

const UsagePage = () => {
  const { teams } = useTeams();
  const { data: organizations = [] } = useOrganizations();
  const { data: projects = [] } = useProjects({ includeNonAdmin: true });

  return (
    <UsagePageView
      teams={teams ?? []}
      organizations={organizations}
      projects={projects}
    />
  );
};

export default UsagePage;
