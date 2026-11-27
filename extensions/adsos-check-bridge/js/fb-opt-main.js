/* Tối ưu Facebook — phần chạy trong NGỮ CẢNH TRANG (world MAIN).
 *
 * ⚠ VÌ SAO PHẢI LÀ MAIN: content script thường chạy ở ngữ cảnh CÁCH LY. Hai ngữ cảnh dùng chung
 * cây DOM nhưng KHÁC hẳn đối tượng window. Vá window.fetch / WebSocket.prototype.send / getter
 * document.hidden ở ngữ cảnh cách ly là vá vào bản sao của riêng mình: công tắc bật mà không chặn
 * gì, lại KHÔNG báo lỗi. Hai công tắc cũ (ẩn bài gợi ý, giữ vị trí bảng tin) nằm ở content.js và
 * chạy được vì chúng chỉ đụng DOM và sự kiện dùng chung — đừng chuyển chúng sang đây.
 *
 * ⚠ CÀI SẴN, KHÔNG CÀI LÚC BẬT: mọi lớp bọc dưới đây gắn NGAY khi tài liệu bắt đầu, rồi mới cổng
 * hành vi bằng cờ `co`. Nếu đợi người dùng bật mới gắn thì lúc đó trang đã giữ tham chiếu tới hàm
 * gốc, vá thành vô nghĩa. Cũng vì vậy KHÔNG bao giờ gỡ lớp bọc ra — chỉ hạ cờ.
 *
 * Cài đặt được ngữ cảnh cách ly gửi sang qua postMessage (xem js/fb-opt-relay.js). File này KHÔNG
 * đọc chrome.* được, và cũng không cần.
 */
(function () {
  "use strict";

  var CHOT = "__fioxFbOptMain__";
  if (window[CHOT]) return;
  window[CHOT] = true;

  var KENH = "EXTFBOPT_CFG"; // tên trung tính, khớp fb-opt-relay.js (xem lý do ở đó)
  // Mặc định TẮT HẾT. Chưa nhận được cài đặt thì không chặn gì — an toàn hơn là chặn nhầm.
  var co = {
    block_seen_chat: false,
    block_typing_chat: false,
    block_seen_story_facebook: false,
    prevent_facebook_feed_reload: false,
  };

  window.addEventListener("message", function (e) {
    // Chỉ nhận thông điệp do chính trang này gửi. Không nhận từ iframe hay cửa sổ khác.
    if (e.source !== window) return;
    var d = e.data;
    if (!d || d.type !== KENH || !d.cfg) return;
    var moi = d.cfg;
    Object.keys(co).forEach(function (k) { co[k] = moi[k] === true; });
  }, false);

  // ⚠ Bắt tay hai nhịp: hai tệp cùng chạy lúc tài liệu bắt đầu, không chắc bên nào xong trước.
  // Gắn xong bộ nghe mới báo sang, rồi bên kia mới gửi cài đặt — khỏi cảnh gửi vào khoảng trống
  // rồi công tắc im ru cho tới lần đổi kế tiếp.
  try { window.postMessage({ type: "EXTFBOPT_READY" }, location.origin); } catch (e) {}

  var DEC = new TextDecoder();
  var ENC = new TextEncoder();

  function jsonHoacNull(s) {
    if (!s) return null;
    try { var o = JSON.parse(s); return o && typeof o === "object" ? o : null; } catch (e) { return null; }
  }
  function uidHienTai() {
    var m = String(document.cookie || "").match(/(?:^|;\s*)c_user=(\d+)/);
    return m ? m[1] : "";
  }

  /* ============ 1. Giữ vị trí bảng tin (phần chỉ làm được ở ngữ cảnh trang) ============
   * content.js đã nuốt sự kiện visibilitychange/focus ở pha bắt. Nhưng Facebook còn HỎI THẲNG
   * document.hidden / document.visibilityState, và câu hỏi đó không đi qua sự kiện nào. Nói dối
   * ngay ở getter thì dù trang có tự hỏi cũng tưởng bạn chưa rời tab. */
  (function vaTrangThaiHienThi() {
    var tHidden = Object.getOwnPropertyDescriptor(Document.prototype, "hidden");
    var tState = Object.getOwnPropertyDescriptor(Document.prototype, "visibilityState");
    try {
      Object.defineProperty(document, "hidden", {
        configurable: true,
        get: function () {
          if (co.prevent_facebook_feed_reload) return false;
          return tHidden && tHidden.get ? tHidden.get.call(this) : false;
        },
      });
    } catch (e) {}
    try {
      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        get: function () {
          if (co.prevent_facebook_feed_reload) return "visible";
          return tState && tState.get ? tState.get.call(this) : "visible";
        },
      });
    } catch (e) {}
  })();

  /* ============ 2. Xem tin (Story) ẩn danh ============
   * Facebook ghi nhận lượt xem bằng một lời gọi mang tên mutation cố định. Chặn đúng lời gọi đó
   * là xem xong không để lại tên, phần còn lại của trang không đụng tới.
   * ⚠ Phải bịt CẢ BA đường: fetch, XMLHttpRequest và sendBeacon. Bịt mỗi fetch là lọt. */
  var DAU_HIEU_STORY = "storiesUpdateSeenStateMutation";

  function doiChuoi(than) {
    if (typeof than === "string") return than;
    if (than instanceof URLSearchParams) return than.toString();
    if (typeof FormData !== "undefined" && than instanceof FormData) {
      var ra = [];
      than.forEach(function (v, k) { ra.push(k + "=" + String(v)); });
      return ra.join("&");
    }
    return "";
  }
  function laLuotXemStory(phuongThuc, than) {
    if (!co.block_seen_story_facebook) return false;
    if (String(phuongThuc || "GET").toUpperCase() !== "POST") return false;
    return doiChuoi(than).indexOf(DAU_HIEU_STORY) >= 0;
  }

  (function vaFetch() {
    var goc = window.fetch;
    if (typeof goc !== "function") return;
    window.fetch = function (dauVao, tuyChon) {
      try {
        var o = tuyChon && typeof tuyChon === "object" ? tuyChon : {};
        var pt = o.method || (typeof Request !== "undefined" && dauVao instanceof Request ? dauVao.method : "GET");
        if (laLuotXemStory(pt, o.body)) {
          // Trả về phản hồi rỗng HỢP LỆ thay vì để lỗi: trang tưởng đã ghi nhận xong nên không
          // thử lại và không hiện lỗi cho người dùng.
          return Promise.resolve(new Response("{}", {
            status: 200, headers: { "content-type": "application/json" },
          }));
        }
      } catch (e) {}
      return goc.apply(this, arguments);
    };
  })();

  (function vaXhr() {
    var moGoc = XMLHttpRequest.prototype.open;
    var guiGoc = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (pt) {
      try { this.__fioxPt = pt; } catch (e) {}
      return moGoc.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function (than) {
      try { if (laLuotXemStory(this.__fioxPt, than)) return; } catch (e) {}
      return guiGoc.apply(this, arguments);
    };
  })();

  (function vaBeacon() {
    if (!navigator.sendBeacon) return;
    var goc = navigator.sendBeacon.bind(navigator);
    navigator.sendBeacon = function (url, than) {
      // sendBeacon luôn là POST.
      try { if (laLuotXemStory("POST", than)) return true; } catch (e) {}
      return goc.apply(null, arguments);
    };
  })();

  /* ============ 3. Ẩn "đã xem" và "đang nhập" trong chat ============
   * Messenger KHÔNG gửi hai tín hiệu này bằng request thường. Chúng đi trong gói MQTT chạy trên
   * WebSocket, nên chặn ở tầng fetch là vô ích — phải đọc từng gói.
   *
   * Gói MQTT: byte đầu là cờ (4 bit cao = loại lệnh, 3 = PUBLISH), tiếp theo là "độ dài còn lại"
   * dạng varint 7 bit, rồi tới thân. Thân của PUBLISH: 2 byte độ dài chủ đề, chuỗi chủ đề, 2 byte
   * mã gói nếu mức bảo đảm > 0, phần còn lại là nội dung.
   * Nội dung của Facebook là JSON. Chủ đề "/ls_req" chở cả hai thứ ta quan tâm. */
  function docVarint(b, i) {
    var n = 0, nhan = 1, byte = 0, dem = 0;
    do {
      if (i + dem >= b.length || dem >= 4) return null;
      byte = b[i + dem++];
      n += (byte & 127) * nhan;
      nhan *= 128;
    } while (byte & 128);
    return { n: n, dem: dem };
  }
  function ghiVarint(n) {
    var ra = [];
    do {
      var d = n % 128;
      n = Math.floor(n / 128);
      if (n > 0) d |= 128;
      ra.push(d);
    } while (n > 0);
    return ra;
  }
  function sangBytes(d) {
    if (d instanceof ArrayBuffer) return new Uint8Array(d);
    if (ArrayBuffer.isView(d)) return new Uint8Array(d.buffer, d.byteOffset, d.byteLength);
    return null; // chuỗi và Blob: không phải gói MQTT nhị phân, bỏ qua
  }
  function bocPublish(b) {
    if (!b || b.length < 2) return null;
    var co1 = b[0];
    if (((co1 >> 4) & 15) !== 3) return null; // chỉ quan tâm PUBLISH
    var v = docVarint(b, 1);
    if (!v) return null;
    var dau = 1 + v.dem;
    if (dau + v.n > b.length) return null; // gói chưa đủ, đừng động vào
    var i = dau;
    var lenChuDe = (b[i] << 8) | b[i + 1];
    i += 2;
    var chuDe = DEC.decode(b.subarray(i, i + lenChuDe));
    i += lenChuDe;
    var qos = (co1 >> 1) & 3;
    var maGoi = 0;
    if (qos > 0) { maGoi = (b[i] << 8) | b[i + 1]; i += 2; }
    return {
      chuDe: chuDe, qos: qos, dup: !!(co1 & 8), retain: !!(co1 & 1),
      maGoi: maGoi, than: b.slice(i, dau + v.n),
    };
  }
  function dungPublish(p) {
    var chuDe = ENC.encode(p.chuDe || "");
    var than = p.than instanceof Uint8Array ? p.than : ENC.encode(String(p.than || ""));
    var conLai = 2 + chuDe.length + (p.qos > 0 ? 2 : 0) + than.length;
    var vi = ghiVarint(conLai);
    var ra = new Uint8Array(1 + vi.length + conLai);
    var i = 0;
    ra[i++] = 0x30 | (p.dup ? 8 : 0) | ((p.qos & 3) << 1) | (p.retain ? 1 : 0);
    for (var k = 0; k < vi.length; k++) ra[i++] = vi[k];
    ra[i++] = (chuDe.length >> 8) & 255;
    ra[i++] = chuDe.length & 255;
    ra.set(chuDe, i); i += chuDe.length;
    if (p.qos > 0) { ra[i++] = (p.maGoi >> 8) & 255; ra[i++] = p.maGoi & 255; }
    ra.set(than, i);
    return ra.buffer;
  }

  function xuLyGoi(p) {
    if (!p || p.chuDe !== "/ls_req" || !p.than || !p.than.length) return { bo: false, sua: false };
    var goc = jsonHoacNull(DEC.decode(p.than));
    if (!goc) return { bo: false, sua: false };

    // Loại 4 = báo "đang gõ". Gói này chỉ chở đúng việc đó nên BỎ CẢ GÓI là xong.
    if (co.block_typing_chat && goc.type === 4) {
      var l1 = jsonHoacNull(goc.payload);
      var l2 = l1 && jsonHoacNull(l1.payload);
      if (l2 && l2.thread_key) return { bo: true, sua: false };
    }

    // Loại 3 = một CHÙM tác vụ; tác vụ mang nhãn "21" là đánh dấu đã đọc.
    if (co.block_seen_chat && goc.type === 3) {
      var than = jsonHoacNull(goc.payload);
      var ds = than && Array.isArray(than.tasks) ? than.tasks : [];
      var uid = uidHienTai();
      if (!uid || !ds.length) return { bo: false, sua: false };
      var doi = false;
      ds.forEach(function (t) {
        if (!t || String(t.label) !== "21") return;
        doi = true;
        // ⚠ KHÔNG bỏ cả gói: chùm này còn chở các tác vụ khác, bỏ hết là hỏng chat.
        // Trỏ mốc đã đọc về cuộc trò chuyện với CHÍNH MÌNH: Facebook vẫn nhận một gói hợp lệ,
        // còn cuộc trò chuyện thật thì không được cập nhật mốc nên người gửi không thấy "đã xem".
        t.payload = JSON.stringify({ thread_id: uid, last_read_watermark_ts: Date.now() * 1000 });
      });
      if (doi) {
        goc.payload = JSON.stringify(than);
        p.than = ENC.encode(JSON.stringify(goc));
        return { bo: false, sua: true };
      }
    }
    return { bo: false, sua: false };
  }

  (function vaWebSocket() {
    var goc = WebSocket.prototype.send;
    if (typeof goc !== "function") return;
    // ⚠ Vá PROTOTYPE.send chứ KHÔNG thay window.WebSocket. Facebook mở kết nối rất sớm; bọc hàm
    // dựng thì mọi socket tạo trước đó thoát sạch. send được tra trên prototype ngay lúc gọi nên
    // vá ở đây bắt được cả những socket đã mở từ trước.
    WebSocket.prototype.send = function (duLieu) {
      if (co.block_seen_chat || co.block_typing_chat) {
        try {
          var b = sangBytes(duLieu);
          var p = b && bocPublish(b);
          if (p) {
            var kq = xuLyGoi(p);
            if (kq.bo) return;                                  // nuốt gói
            if (kq.sua) return goc.call(this, dungPublish(p));   // gửi bản đã sửa
          }
        } catch (e) { /* gói lạ thì để nguyên, tuyệt đối không làm hỏng chat */ }
      }
      return goc.apply(this, arguments);
    };
  })();
})();
