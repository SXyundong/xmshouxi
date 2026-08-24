import DepartmentChat from '@/components/DepartmentChat';

export default function InventoryPage() {
  return (
    <DepartmentChat
      department="inventory"
      name="库存Agent"
      emoji="📦"
      description="库存查询与管理"
    />
  );
}
