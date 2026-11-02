// Chạy THẬT phần dữ liệu của sơ đồ trong node, thay vì dò bằng regex.
// Lỗi thiếu dấu phẩy giữa hai mảng cột là JS HỢP LỆ — nó thành phép đánh chỉ
// số và trả về undefined — nên `node --check` không bắt được. Chỉ có chạy mới
// thấy.
const fs = require('fs');
const html = fs.readFileSync('docs/database_erd.html', 'utf8');

function grab(name) {
  const i = html.indexOf(`const ${name} = [`);
  if (i < 0) throw new Error(`không thấy ${name}`);
  let d = 0, j = html.indexOf('[', i);
  const start = j;
  for (; j < html.length; j++) {
    if (html[j] === '[') d++;
    else if (html[j] === ']') { d--; if (d === 0) break; }
  }
  return eval(html.slice(start, j + 1));
}

const TABLES = grab('TABLES');
const RELS = grab('RELS');

console.log(`TABLES: ${TABLES.length} bảng`);
console.log(`RELS:   ${RELS.length} quan hệ`);

let bad = 0;
TABLES.forEach((t, i) => {
  if (!t || typeof t !== 'object') { console.log(`  ✗ TABLES[${i}] không phải đối tượng: ${t}`); bad++; return; }
  if (!t.id) { console.log(`  ✗ TABLES[${i}] thiếu id`); bad++; }
  if (!Array.isArray(t.cols)) { console.log(`  ✗ ${t.id} cols không phải mảng`); bad++; return; }
  t.cols.forEach((col, k) => {
    // Đây là chỗ lỗi thiếu dấu phẩy hiện ra: phần tử thành undefined.
    if (!Array.isArray(col) || col.length < 3 || col.length > 4
        || typeof col[0] !== 'string') {
      console.log(`  ✗ ${t.id}.cols[${k}] không hợp lệ: ${JSON.stringify(col)}`);
      bad++;
      return;
    }
    // Phần tử thứ tư là danh sách giá trị ENUM, ngăn bằng '|'. Chỉ cột
    // ENUM/SET được có nó, và không giá trị nào được rỗng — một dấu '|' lạc
    // sẽ sinh ra một ô giá trị trống trên sơ đồ mà không ai để ý.
    if (col.length === 4) {
      if (!/^(ENUM|SET)$/.test(col[1])) {
        console.log(`  ✗ ${t.id}.${col[0]}: có danh sách giá trị nhưng kiểu là ${col[1]}`);
        bad++;
      }
      if (typeof col[3] !== 'string' || col[3] === ''
          || col[3].split('|').some(v => v === '')) {
        console.log(`  ✗ ${t.id}.${col[0]}: danh sách giá trị hỏng: ${JSON.stringify(col[3])}`);
        bad++;
      }
    } else if (/^(ENUM|SET)$/.test(col[1])) {
      console.log(`  ✗ ${t.id}.${col[0]}: kiểu ${col[1]} nhưng thiếu danh sách giá trị`);
      bad++;
    }
  });
  if (typeof t.x !== 'number' || typeof t.y !== 'number') {
    console.log(`  ✗ ${t.id} thiếu toạ độ`); bad++;
  }
});

RELS.forEach((r, i) => {
  if (!Array.isArray(r) || r.length !== 5) { console.log(`  ✗ RELS[${i}] sai dạng: ${JSON.stringify(r)}`); bad++; return; }
  const ids = TABLES.map(t => t.id);
  if (!ids.includes(r[0])) { console.log(`  ✗ RELS[${i}] bảng nguồn lạ: ${r[0]}`); bad++; }
  if (!ids.includes(r[2])) { console.log(`  ✗ RELS[${i}] bảng đích lạ: ${r[2]}`); bad++; }
  const src = TABLES.find(t => t.id === r[0]);
  if (src && !src.cols.some(c => Array.isArray(c) && c[0] === r[1])) {
    console.log(`  ✗ RELS[${i}] ${r[0]} không có cột ${r[1]}`); bad++;
  }
});

/* ── Hình học: thẻ có chồng nhau không, có tràn khung không ──
   Toạ độ thẻ ghi CỐ ĐỊNH trong tệp, còn chiều cao thì phụ thuộc số cột và
   số dòng giá trị ENUM. Thêm một giá trị ENUM vào cột `nutrient` là thẻ cao
   thêm một dòng, và thẻ bên dưới bị đè mà không có gì báo. Đúng chuyện đã
   xảy ra: `condition_rules` đè `rda_reference` 59 px ngay khi bật hiển thị
   giá trị ENUM.

   Chiều cao ở đây là ƯỚC LƯỢNG từ CSS (đầu thẻ 36, dòng 22, dòng giá trị
   ~12,3 mỗi hàng chữ), không phải số đo từ trình duyệt. Nó dùng để bắt lỗi
   rõ ràng, nên ngưỡng cảnh báo đặt ở 20 px để sai số ước lượng không gây báo
   động giả. */
const CW = 280, HEAD = 36, BODY_PAD = 8, ROW = 22;
const INNER = CW - 24, CHAR = 4.9, LINE = 12.3, MIN_GAP = 20;

function cardHeight(t) {
  let h = HEAD + BODY_PAD;
  for (const c of t.cols) {
    if (Array.isArray(c) && c.length === 4) {
      const text = c[3].split('|').join('   ·   ');
      h += ROW + Math.max(1, Math.ceil(text.length * CHAR / INNER)) * LINE + 4;
    } else h += ROW;
  }
  return Math.round(h);
}

const boxes = TABLES.map(t => ({ id: t.id, x: t.x, y: t.y, h: cardHeight(t) }));
for (let i = 0; i < boxes.length; i++) {
  for (let j = i + 1; j < boxes.length; j++) {
    const a = boxes[i], b = boxes[j];
    if (Math.abs(a.x - b.x) >= CW) continue;
    const gap = Math.max(a.y, b.y) - Math.min(a.y + a.h, b.y + b.h);
    if (gap < 0) {
      console.log(`  ✗ thẻ ${a.id} và ${b.id} chồng nhau ${-gap} px`);
      bad++;
    } else if (gap < MIN_GAP) {
      console.log(`  ✗ thẻ ${a.id} và ${b.id} chỉ cách nhau ${gap} px`);
      bad++;
    }
  }
}

const needRight = Math.max(...boxes.map(b => b.x + CW));
const needBottom = Math.max(...boxes.map(b => b.y + b.h));
const canvas = html.match(/#canvas\s*\{[^}]*width:(\d+)px;\s*height:(\d+)px/);
if (!canvas) {
  console.log('  ✗ không đọc được kích thước #canvas');
  bad++;
} else {
  const [w, h] = [Number(canvas[1]), Number(canvas[2])];
  if (needBottom > h) {
    console.log(`  ✗ nội dung cao ${needBottom} px, #canvas chỉ ${h} px — thẻ cuối bị cắt`);
    bad++;
  }
  if (needRight > w) {
    console.log(`  ✗ nội dung rộng ${needRight} px, #canvas chỉ ${w} px`);
    bad++;
  }
  console.log(`Khung: cần ${needRight}×${needBottom}, khai ${w}×${h} px`);
}

const totalCols = TABLES.reduce((s, t) => s + t.cols.length, 0);
const enumCols = TABLES.reduce(
  (s, t) => s + t.cols.filter(c => Array.isArray(c) && c.length === 4).length, 0);
const enumVals = TABLES.reduce(
  (s, t) => s + t.cols.filter(c => Array.isArray(c) && c.length === 4)
                      .reduce((a, c) => a + c[3].split('|').length, 0), 0);
console.log(`Tổng cột vẽ ra: ${totalCols}`);
console.log(`Cột ENUM/SET:   ${enumCols} cột, ${enumVals} giá trị`);
console.log(bad === 0 ? '✓ dữ liệu sơ đồ dựng được hoàn toàn' : `✗ ${bad} vấn đề`);
process.exit(bad === 0 ? 0 : 1);
