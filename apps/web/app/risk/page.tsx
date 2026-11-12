"use client";

import { useEffect, useState } from "react";
import { fetchJson, postJson } from "../../lib/api";

type Risk = {account_id: string; currency: string | null; debt: string | null; debt_threshold: string | null; locked: boolean; risk_code: string; data_status: string; last_error: string | null};
const labels: Record<string,string> = {UNKNOWN:"Chưa kiểm tra",HEALTHY:"Hoạt động",DISABLED:"Vô hiệu hóa",UNSETTLED:"Vấn đề thanh toán",HIGH_DEBT:"Nợ vượt ngưỡng",RESTRICTED:"Hạn chế"};

export default function RiskPage() {
  const [rows,setRows] = useState<Risk[]>([]);
  const [notice,setNotice] = useState("");
  const [busy,setBusy] = useState(false);
  const [thresholds,setThresholds] = useState<Record<string,string>>({});
  async function load() {setRows(await fetchJson<Risk[]>("/meta-risk"));}
  useEffect(() => {load().catch(() => setNotice("Không tải được dữ liệu rủi ro."));},[]);
  async function action(path:string,body:unknown={}) {
    setBusy(true);
    try {const result = await postJson<{message?:string;checked?:number;errors?:number}>(path,body); setNotice(result.message ?? `Đã kiểm tra ${result.checked ?? 0} tài khoản; ${result.errors ?? 0} tài khoản chưa xác minh.`); await load();}
    catch {setNotice("Thao tác chưa hoàn tất. Kiểm tra trạng thái và quyền kết nối Meta.");}
    finally {setBusy(false);}
  }
  return <div className="w-full space-y-6">
    <h1>Giám sát rủi ro tài khoản</h1>
    <p>Quét tự động mỗi 5 phút. Ngưỡng nợ cước do quản trị viên đặt theo từng tiền tệ. Đặc cách vi phạm không vượt qua khóa an toàn.</p>
    <p>Lệnh khóa chặn tạo và bật chiến dịch ngay trong hệ thống, sau đó gửi lệnh tạm dừng Meta khi quyền ghi đã được bật. Chế độ giả lập không dừng chiến dịch thật.</p>
    <button disabled={busy} onClick={() => action("/meta-risk/scan")}>Kiểm tra ngay</button>
    {notice && <p role="status">{notice}</p>}
    {rows.length === 0 ? <p>Chưa có dữ liệu kiểm tra.</p> : <table style={{width:"100%",marginTop:24}}><thead><tr><th>Tài khoản</th><th>Tình trạng</th><th>Nợ cước</th><th>Ngưỡng cảnh báo</th><th>Khóa an toàn</th></tr></thead><tbody>
    {rows.map(row => <tr key={row.account_id}><td>{row.account_id}</td><td>{labels[row.risk_code] ?? "Chưa xác định"}{row.data_status !== "VERIFIED" && <p>Chưa xác minh — giữ dữ liệu cũ</p>}{row.last_error && <p>{row.last_error}</p>}</td><td>{row.debt ?? "Chưa có"} {row.currency}</td><td><input aria-label={`Ngưỡng nợ ${row.account_id}`} type="number" min="0" step="any" value={thresholds[row.account_id] ?? row.debt_threshold ?? ""} onChange={e => setThresholds({...thresholds,[row.account_id]:e.target.value})}/><button disabled={busy || !row.currency || !(thresholds[row.account_id] ?? row.debt_threshold)} onClick={() => action(`/meta-risk/${row.account_id}/threshold`,{threshold:thresholds[row.account_id] ?? row.debt_threshold})}>Lưu ngưỡng</button></td><td><p>{row.locked ? "Đang khóa" : "Chưa khóa"}</p><button disabled={busy} onClick={() => action(`/meta-risk/${row.account_id}/lock`)}>Khóa và dừng chiến dịch</button></td></tr>)}
    </tbody></table>}
  </div>;
}
