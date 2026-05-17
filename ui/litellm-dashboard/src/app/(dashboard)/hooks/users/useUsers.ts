import { userListCall, UserListResponse } from "@/components/networking";
import { useInfiniteQuery } from "@tanstack/react-query";
import { createQueryKeys } from "../common/queryKeysFactory";
import { all_admin_roles, internalUserRoles } from "@/utils/roles";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import { useCavadaLabsKeyContextOptions } from "@/components/cavadalabs/keyContext";
import { resolveCavadaLabsProductContext } from "@/components/cavadalabs/productContext";

const infiniteUsersKeys = createQueryKeys("infiniteUsers");

const DEFAULT_PAGE_SIZE = 50;

export const useInfiniteUsers = (pageSize: number = DEFAULT_PAGE_SIZE, searchEmail?: string) => {
  const { accessToken, userRole } = useAuthorized();
  const cavadalabsContext = useCavadaLabsKeyContextOptions(accessToken);
  const { companies: cavadalabsCompanies, projects: cavadalabsProjects } = cavadalabsContext;
  const cavadalabsProductContext = resolveCavadaLabsProductContext(cavadalabsContext);
  const hasCavadaLabsUserScope = cavadalabsProductContext.isCavadaLabsProductContext;
  const cavadalabsCompanyIds = cavadalabsCompanies.map((company) => company.company_id);
  const cavadalabsProjectIds = cavadalabsProjects.map((project) => project.project_id);
  const hasCavadaLabsMembershipOptions = cavadalabsCompanyIds.length > 0 || cavadalabsProjectIds.length > 0;
  const canListUsers =
    all_admin_roles.includes(userRole!) ||
    (cavadalabsProductContext.contextKnown &&
      hasCavadaLabsUserScope &&
      hasCavadaLabsMembershipOptions &&
      internalUserRoles.includes(userRole!));
  return useInfiniteQuery<UserListResponse>({
    queryKey: infiniteUsersKeys.list({
      filters: {
        pageSize,
        ...(searchEmail && { searchEmail }),
        ...(hasCavadaLabsUserScope && {
          cavadalabsCompanyIds: cavadalabsCompanyIds.join(","),
          cavadalabsProjectIds: cavadalabsProjectIds.join(","),
        }),
      },
    }),
    queryFn: async ({ pageParam }) => {
      if (hasCavadaLabsUserScope) {
        return await userListCall(
          accessToken!,
          null,
          pageParam as number,
          pageSize,
          searchEmail || null,
          null,
          null,
          null,
          null,
          null,
          null,
          cavadalabsCompanyIds,
          cavadalabsProjectIds,
        );
      }
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
