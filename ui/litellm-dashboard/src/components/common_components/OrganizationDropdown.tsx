import React from "react";
import { Select, Typography } from "antd";
import { Organization } from "../networking";

const { Text } = Typography;

interface OrganizationDropdownProps {
  organizations?: Organization[] | null;
  value?: string;
  onChange?: (value: string) => void;
  id?: string;
  disabled?: boolean;
  loading?: boolean;
  style?: React.CSSProperties;
}

export const getCompanyDisplayName = (organization: Organization): string => {
  return organization.company_name || organization.organization_alias || organization.company_id || organization.organization_id;
};

export const getCompanyDisplayId = (organization: Organization): string => {
  return organization.company_id || organization.organization_id;
};

const OrganizationDropdown: React.FC<OrganizationDropdownProps> = ({
  organizations,
  value,
  onChange,
  id,
  disabled,
  loading,
  style,
}) => {
  return (
    <Select
      id={id}
      showSearch
      placeholder="All Companies"
      value={value}
      onChange={onChange}
      disabled={disabled}
      loading={loading}
      allowClear
      style={{ minWidth: 280, ...style }}
      filterOption={(input, option) => {
        if (!option) return false;
        const org = organizations?.find((o) => o.organization_id === option.key);
        if (!org) return false;

        const searchTerm = input.toLowerCase().trim();
        const companyName = getCompanyDisplayName(org).toLowerCase();
        const companyId = getCompanyDisplayId(org).toLowerCase();

        return companyName.includes(searchTerm) || companyId.includes(searchTerm);
      }}
    >
      {organizations?.map((org) => {
        const companyName = getCompanyDisplayName(org);
        const companyId = getCompanyDisplayId(org);
        return (
          <Select.Option key={org.organization_id} value={org.organization_id}>
            <span className="font-medium">{companyName}</span> <Text type="secondary">({companyId})</Text>
          </Select.Option>
        );
      })}
    </Select>
  );
};

export default OrganizationDropdown;
