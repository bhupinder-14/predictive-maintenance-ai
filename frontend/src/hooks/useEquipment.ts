import { useInfiniteQuery } from "@tanstack/react-query";
import { getEquipment } from "@/api/equipment";

const EQUIPMENT_PAGE_SIZE = 100;

export function useEquipment() {
  return useInfiniteQuery({
    queryKey: ["equipment-list"],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => getEquipment(EQUIPMENT_PAGE_SIZE, pageParam),
    getNextPageParam: (lastPage, pages) => lastPage.length === EQUIPMENT_PAGE_SIZE ? pages.length * EQUIPMENT_PAGE_SIZE : undefined,
    staleTime: 30_000,
    retry: false,
  });
}

export { EQUIPMENT_PAGE_SIZE };
