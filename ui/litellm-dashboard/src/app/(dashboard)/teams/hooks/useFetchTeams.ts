import { useCallback, useEffect, useState } from "react";
import { fetchTeams } from "@/components/common_components/fetch_teams";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import { Organization, Team, v2TeamListCall } from "@/components/networking";

interface useFetchTeamsProps {
  currentOrg: Organization | null;
  setTeams: (teams: Team[] | null) => void;
  isCavadaLabsProductContext?: boolean;
}

const useFetchTeams = ({ currentOrg, setTeams, isCavadaLabsProductContext = false }: useFetchTeamsProps) => {
  const [lastRefreshed, setLastRefreshed] = useState("");
  const { accessToken, userId, userRole } = useAuthorized();

  const onRefreshClick = useCallback(() => {
    const currentDate = new Date();
    setLastRefreshed(currentDate.toLocaleString());
  }, []);

  useEffect(() => {
    if (accessToken) {
      if (isCavadaLabsProductContext) {
        v2TeamListCall(accessToken, null, null, null, null, 1, 10, "created_at", "desc", null, null).then(
          (response) => {
            setTeams(response.teams ?? []);
          },
        );
      } else {
        fetchTeams(accessToken, userId, userRole, currentOrg, setTeams).then();
      }
    }
    onRefreshClick();
  }, [accessToken, currentOrg, isCavadaLabsProductContext, lastRefreshed, onRefreshClick, setTeams, userId, userRole]);

  return { lastRefreshed, setLastRefreshed, onRefreshClick };
};

export default useFetchTeams;
