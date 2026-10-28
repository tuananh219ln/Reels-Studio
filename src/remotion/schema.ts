// Dữ liệu đầu vào của 1 video. Claude sẽ sinh đúng cấu trúc này dưới dạng JSON.
// Trong chữ, bọc từ khóa bằng **...** để tô đỏ, ví dụ "**XƯƠNG CHẮC KHỎE**".

export type Scene = {
  title: string; // tên món, hiện trong hộp vàng
  benefit: string; // 1 dòng lợi ích, hiện dưới hộp vàng
  seconds: number;
  image?: string; // tên file trong public/photos/; bỏ trống = dùng nền tạm
  emoji?: string; // biểu tượng trên nền tạm khi chưa có ảnh
};

export type ReelProps = {
  hook: {
    lines: string[]; // 3–5 dòng tiêu đề trong hộp vàng
    seconds: number;
    image?: string;
    emoji?: string;
  };
  scenes: Scene[];
  outro: {
    text: string;
    seconds: number;
  };
  disclaimer: string; // hiện suốt video, cỡ nhỏ
  music?: string; // tên file trong public/music/
  musicVolume?: number; // 0–1, mặc định 0.25
};

export const totalSeconds = (p: ReelProps) =>
  p.hook.seconds + p.scenes.reduce((s, x) => s + x.seconds, 0) + p.outro.seconds;
