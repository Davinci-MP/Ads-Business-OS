"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { fetchJson, getAdsCheckData, getSyncedBMs, getVias, type SyncedAdAccount } from "../lib/api";
import type { AssetData, Customer } from "../types/admin";

const initial: AssetData = { accounts: [], bms: [], vias: [], stats: null, customers: [] };
const Context = createContext<{ data: AssetData; loading: boolean; errors: string[]; reload: () => Promise<void> }>({ data: initial, loading: true, errors: [], reload: async () => {} });

export async function loadAllAccounts() {
  const first = await getAdsCheckData({ tab: "accounts", page: 1, page_size: 500 });
  const items = first.items as SyncedAdAccount[];
  for (let page = 2; page <= first.total_pages; page++) {
    const next = await getAdsCheckData({ tab: "accounts", page, page_size: 500 });
    if (!next.items.length) throw new Error("Danh sách TKQC chưa đầy đủ; giữ dữ liệu trước đó.");
    items.push(...next.items as SyncedAdAccount[]);
  }
  return items;
}

export function AdminDataProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState(initial);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<string[]>([]);
  const reload = useCallback(async () => {
    setLoading(true);
    const results = await Promise.allSettled([loadAllAccounts(), getSyncedBMs(), getVias(), fetchJson<Customer[]>("/customers")]);
    const [accounts, bms, vias, customers] = results;
    setData(previous => ({
      accounts: accounts.status === "fulfilled" ? accounts.value : previous.accounts,
      bms: bms.status === "fulfilled" ? bms.value.bms : previous.bms,
      vias: vias.status === "fulfilled" ? vias.value.vias : previous.vias,
      stats: vias.status === "fulfilled" ? vias.value.stats : previous.stats,
      customers: customers.status === "fulfilled" ? customers.value : previous.customers,
    }));
    setErrors(results.flatMap((result, i) => result.status === "rejected" ? [`${["TKQC", "BM", "VIA", "Khách hàng"][i]}: ${result.reason instanceof Error ? result.reason.message : "Không thể tải dữ liệu"}`] : []));
    setLoading(false);
  }, []);
  useEffect(() => { void reload(); }, [reload]);
  return <Context.Provider value={{ data, loading, errors, reload }}>{children}</Context.Provider>;
}
export const useAdminData = () => useContext(Context);
