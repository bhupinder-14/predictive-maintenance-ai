import { useInfiniteQuery } from "@tanstack/react-query";
import { getEquipmentHistory } from "@/api/equipment";

const HISTORY_PAGE_SIZE = 50;

export function useEquipmentHistory(equipmentId: number | null) {
  return useInfiniteQuery({
    queryKey: ["equipment-history", equipmentId],
    enabled: equipmentId !== null,
    initialPageParam: 0,
    queryFn: ({ pageParam }) => {
      if (equipmentId === null) throw new Error("Select equipment to load history.");
      return getEquipmentHistory(equipmentId, HISTORY_PAGE_SIZE, pageParam);
    },
    getNextPageParam: (lastPage, pages) => lastPage.items.length === HISTORY_PAGE_SIZE ? pages.length * HISTORY_PAGE_SIZE : undefined,
    staleTime: 15_000,
    retry: false,
  });
}

export { HISTORY_PAGE_SIZE };
