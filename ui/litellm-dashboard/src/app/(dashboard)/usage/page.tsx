"use client";

import UsagePageView from "@/components/UsagePage/components/UsagePageView";
import useTeams from "@/app/(dashboard)/hooks/useTeams";

const UsagePage = () => {
  const { teams } = useTeams();

  return <UsagePageView teams={teams ?? []} />;
};

export default UsagePage;
