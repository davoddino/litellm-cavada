import { userListCall, UserListResponse } from "@/components/networking";
import { useInfiniteQuery } from "@tanstack/react-query";
import { createQueryKeys } from "../common/queryKeysFactory";
import { all_admin_roles, internalUserRoles } from "@/utils/roles";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import { useCavadaLabsKeyContextOptions } from "@/components/cavadalabs/keyContext";

const infiniteUsersKeys = createQueryKeys("infiniteUsers");

const DEFAULT_PAGE_SIZE = 50;

export const useInfiniteUsers = (pageSize: number = DEFAULT_PAGE_SIZE, searchEmail?: string) => {
  const { accessToken, userRole } = useAuthorized();
  const {
    companies: cavadalabsCompanies,
    projects: cavadalabsProjects,
    isLoading: isLoadingCavadaLabsScope,
  } = useCavadaLabsKeyContextOptions(accessToken);
  const hasCavadaLabsUserScope = cavadalabsCompanies.length > 0 || cavadalabsProjects.length > 0;
  const canListUsers =
    all_admin_roles.includes(userRole!) ||
    (!isLoadingCavadaLabsScope && hasCavadaLabsUserScope && internalUserRoles.includes(userRole!));
  return useInfiniteQuery<UserListResponse>({
    queryKey: infiniteUsersKeys.list({
      filters: {
        pageSize,
        ...(searchEmail && { searchEmail }),
        ...(hasCavadaLabsUserScope && {
          cavadalabsCompanyIds: cavadalabsCompanies.map((company) => company.company_id),
          cavadalabsProjectIds: cavadalabsProjects.map((project) => project.project_id),
        }),
      },
    }),
    queryFn: async ({ pageParam }) => {
      return await userListCall(
        accessToken!,
        null, // userIDs
        pageParam as number, // page
        pageSize, // page_size
        searchEmail || null, // userEmail
      );
    },
    initialPageParam: 1,
    getNextPageParam: (lastPage) => {
      if (lastPage.page < lastPage.total_pages) {
        return lastPage.page + 1;
      }
      return undefined;
    },
    enabled: Boolean(accessToken) && canListUsers,
  });
};
