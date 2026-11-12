"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useAdminData } from "../../components/admin-data";
import { Empty, ErrorNotice, Metric, PageHeading, Pagination, useToast } from "../../components/admin-ui";
import { togglePrimaryRentalBM } from "../../lib/api";
export default function BusinessManagersPage() {
  const { data, loading, errors, reload } = useAdminData();
  const toast = useToast();
  const [search,setSearch] = useState("");
  const [filter,setFilter] = useState("all");
  const [page,setPage] = useState(1);
  const [size,setSize] = useState(20);
  const [busy,setBusy] = useState<string | null>(null);
  const rows = data.bms.filter(b => (!search || `${b.name} ${b.bm_id} ${b.via_uid}`.toLowerCase().includes(search.toLowerCase())) && (filter !== "primary" || b.is_primary_rental));
  useEffect(() => setPage(1), [search,filter,size]);
  const toggle = async (id:string, current:boolean) => { setBusy(id); try { await togglePrimaryRentalBM(id,!current); toast("Đã cập nhật vai trò BM cho thuê."); await reload(); } catch(e) { toast(e instanceof Error ? e.message : "Không thể cập nhật BM.","error"); } finally { setBusy(null); } };
  return <><PageHeading eyebrow="TÀI SẢN DOANH NGHIỆP" title="Business Manager" description="Quản lý cấu trúc doanh nghiệp và các hồ sơ VIA đang nắm quyền truy cập." actions={<><Link className="btn" href="/clients">Định tuyến khách hàng ↗</Link><button className="btn primary" disabled={loading} onClick={() => void reload()}>↻ Làm mới</button></>}/><ErrorNotice message={errors.join(" · ") || null}/><div className="metric-grid"><Metric label="Tổng Business Manager" value={loading ? "—" : data.bms.length} note="BM đã đồng bộ về hệ thống" icon=""/><Metric label="BM cho thuê chính" value={data.bms.filter(b=>b.is_primary_rental).length} note="Được chọn cho luồng cho thuê" tone="emerald"/><Metric label="VIA quản lý" value={new Set(data.bms.map(b=>b.via_profile_id).filter(Boolean)).size} note="Hồ sơ đã liên kết với BM" icon=""/><Metric label="Tài khoản thuộc BM" value={data.accounts.filter(a=>a.bm_id).length} note="Tài khoản đã đồng bộ, không gộp số tiền" icon=""/></div><section className="panel"><div className="filter-bar"><input aria-label="Tìm BM" placeholder="Tìm tên, mã BM hoặc UID VIA…" value={search} onChange={e=>setSearch(e.target.value)}/><select aria-label="Lọc BM" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">Tất cả BM</option><option value="primary">BM cho thuê chính</option></select></div>{rows.length ? <div className="table-scroll"><table><thead><tr><th>Business Manager</th><th>VIA quản lý</th><th>TKQC</th><th>Trạng thái</th><th>Cho thuê chính</th></tr></thead><tbody>{rows.slice((page-1)*size,page*size).map(b=><tr key={b.id}><td><strong>{b.name}</strong><span className="table-muted mono">{b.bm_id}</span></td><td>{b.via_profile_name || "Chưa có"}<small className="table-muted mono">{b.via_uid}</small></td><td>{b.ad_account_count}</td><td><span className={`pill ${b.status === "ACTIVE" ? "good" : "warn"}`}>{b.status === "ACTIVE" ? "Hoạt động" : "Cần kiểm tra"}</span></td><td><button className={`btn ${b.is_primary_rental ? "active" : ""}`} disabled={busy===b.bm_id} onClick={()=>void toggle(b.bm_id,b.is_primary_rental)}>{b.is_primary_rental ? " Đang chọn" : "Chọn làm BM chính"}</button></td></tr>)}</tbody></table></div>:<Empty description={loading ? "Đang đọc dữ liệu BM…" : "Không tìm thấy BM. Đồng bộ tài sản tại trang Dàn VIA."} action={<Link className="btn" href="/vias">Mở dàn VIA</Link>}/>}<Pagination total={rows.length} page={page} size={size} onPage={setPage} onSize={setSize}/></section></>;
}
