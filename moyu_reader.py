import os
import json
import tkinter as tk
from tkinter import filedialog, messagebox, colorchooser
from tkinter import ttk
import keyboard  # 用于全局热键 (老板键)
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import threading

class MoyuReader:
    def __init__(self, root):
        self.root = root
        self.root.title("Moyu Reader")

        # --- 窗口基础设置 ---
        self.root.overrideredirect(True)  # 无边框
        self.root.attributes("-topmost", True)  # 窗口置顶

        # 默认配置
        self.bg_color = '#000000'
        self.fg_color = '#A9B7C6'
        self.alpha = 0.6
        self.font = ("微软雅黑", 12)
        self.lines_per_page = 3
        self.hotkey = 'alt+shift+h'

        self.root.attributes("-alpha", self.alpha)
        self.root.configure(bg=self.bg_color)

        # --- 变量与状态 ---
        self.filepath = ""
        self.content_lines = []
        self.current_line_idx = 0
        self.is_hidden = False
        self.history = [] # 历史记录 {path, line_idx}

        # --- UI 组件 ---
        self.text_widget = tk.Text(
            self.root,
            font=self.font,
            fg=self.fg_color,
            bg=self.bg_color,
            wrap=tk.WORD,
            bd=0,
            highlightthickness=0,
            state=tk.DISABLED,
            cursor="arrow"
        )
        self.text_widget.pack(fill="both", expand=True, padx=5, pady=2)

        self.sizegrip = ttk.Sizegrip(self.root)
        self.sizegrip.place(relx=1.0, rely=1.0, anchor="se")

        # --- 事件绑定 ---
        self.text_widget.bind("<Button-1>", self.start_move)
        self.text_widget.bind("<B1-Motion>", self.on_motion)

        self.sizegrip.bind("<Button-1>", self.start_resize)
        self.sizegrip.bind("<B1-Motion>", self.on_resize)

        self.root.bind("<MouseWheel>", self.on_mouse_wheel)
        self.text_widget.bind("<MouseWheel>", self.on_mouse_wheel)
        self.root.bind("<Up>", lambda e: self.turn_page(-1))
        self.root.bind("<Down>", lambda e: self.turn_page(1))
        self.text_widget.bind("<Double-Button-1>", lambda e: self.quick_hide())

        self.build_menu()
        self.root.geometry("400x100+100+100")

        # 加载进度
        self.load_progress()
        self.bind_hotkey()
        self.update_display()

        if not self.content_lines:
             self._set_text("[右键载入历史记录]    [双击隐藏]\n请右键开启您的摸鱼之旅...")

    def _set_text(self, text):
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.delete("1.0", tk.END)
        self.text_widget.insert(tk.END, text)
        self.text_widget.config(state=tk.DISABLED)

    # --- 菜单逻辑 ---
    def build_menu(self):
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="📂 载入 TXT/EPUB", command=self.load_file)

        # 历史记录子菜单
        self.history_menu = tk.Menu(self.menu, tearoff=0)
        self.menu.add_cascade(label="📜 历史记录", menu=self.history_menu)

        self.menu.add_separator()
        self.menu.add_command(label="➕ 增加显示行数", command=lambda: self.change_lines(1))
        self.menu.add_command(label="➖ 减少显示行数", command=lambda: self.change_lines(-1))
        self.menu.add_command(label="🎨 更改字体颜色", command=self.change_fg_color)
        self.menu.add_separator()
        self.menu.add_command(label="👁️ 增加透明度", command=lambda: self.change_alpha(0.1))
        self.menu.add_command(label="👻 减少透明度", command=lambda: self.change_alpha(-0.1))
        self.menu.add_separator()
        self.menu.add_command(label="⚙️ 自定义老板键 (一键隐藏)", command=self.show_settings)
        self.menu.add_separator()
        self.menu.add_command(label="ℹ️ 关于与操作说明", command=self.show_about)
        self.menu.add_command(label="❌ 退出并记忆进度", command=self.quit_app)

        self.text_widget.bind("<Button-3>", self.show_menu)

    def update_history_menu(self):
        self.history_menu.delete(0, tk.END)
        if not self.history:
            self.history_menu.add_command(label="(暂无记录)", state="disabled")
            return

        # 闭包绑定函数
        def load_history_command(path):
            return lambda: self.load_history_file(path)

        for idx, item in enumerate(self.history):
            path = item.get('path', '')
            if not path: continue
            filename = os.path.basename(path)
            self.history_menu.add_command(label=f"📖 {filename}", command=load_history_command(path))

    def show_menu(self, event):
        self.update_history_menu()
        self.menu.tk_popup(event.x_root, event.y_root)

    # --- 热键与录制逻辑 ---
    def bind_hotkey(self):
        try:
            keyboard.unhook_all()
            keyboard.add_hotkey(self.hotkey, self.toggle_visibility)
        except Exception:
            pass

    def show_settings(self):
        # 使用录制方式代替输入框
        setting_win = tk.Toplevel(self.root)
        setting_win.title("录制快捷键")
        setting_win.geometry("320x150")
        setting_win.attributes("-topmost", True)
        setting_win.grab_set()  # 模态窗口拦截其他操作

        tk.Label(setting_win, text="请直接在键盘上按下您想要的隐藏组合键", font=("微软雅黑", 10)).pack(pady=15)
        lbl_result = tk.Label(setting_win, text="[ 正在监听按键... ]", font=("微软雅黑", 14, "bold"), fg="red")
        lbl_result.pack()

        def record():
            try:
                # 录制热键
                hotkey = keyboard.read_hotkey(suppress=False)

                def update_ui():
                    lbl_result.config(text=hotkey, fg="green")
                    self.hotkey = hotkey
                    self.bind_hotkey()
                    self.save_progress()
                    setting_win.after(1000, setting_win.destroy) # 延迟1秒关闭窗口

                setting_win.after(0, update_ui)
            except Exception:
                pass

        threading.Thread(target=record, daemon=True).start()

    # --- 拖拽与缩放逻辑 ---


    def show_about(self):
        import webbrowser
        about_text = """【Moyu Reader 摸鱼阅读器】 v1.0.0

一款专为职场人打造的隐蔽式阅读神器。

📖 基础操作：
  • 鼠标滚轮滚一滚：丝滑翻页
  • 按住文字拖一拖：移动位置
  • 右下角拉一拉：调整大小
  • 鼠标右键：呼出菜单

🚨 隐藏救命技：
  • 左键双击阅读区域：瞬间消失
  • 老板键快捷键：使用全局按键呼叫/隐藏

💾 其他特性：
  • 纯离线自动保存进度，并且每本书进度独立！

🔗 源码与更新：
  GitHub: https://github.com/noc228076/MoyuReader
（点击确定后，如果您想访问 GitHub 可以手动前往）"""
        
        # 创建一个自定义弹窗以支持点击链接（如果需要真正的超链接，这里用简单多按键实现，为了保持轻量直接展示URL即可）
        messagebox.showinfo("关于与使用说明", about_text)

    def start_move(self, event):
        self.x = event.x
        self.y = event.y

    def on_motion(self, event):
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")

    def start_resize(self, event):
        self.resize_x = event.x_root
        self.resize_y = event.y_root
        self.start_width = self.root.winfo_width()
        self.start_height = self.root.winfo_height()

    def on_resize(self, event):
        deltax = event.x_root - self.resize_x
        deltay = event.y_root - self.resize_y
        new_width = max(150, self.start_width + deltax)
        new_height = max(50, self.start_height + deltay)
        self.root.geometry(f"{new_width}x{new_height}")

    # --- 核心阅读逻辑 (支持 TXT 和 EPUB) ---
    def add_to_history(self):
        if not self.filepath: return
        # 移除已有的重复项
        self.history = [item for item in self.history if item.get('path') != self.filepath]
        # 添加到头部
        self.history.insert(0, {'path': self.filepath, 'line_idx': self.current_line_idx})
        # 限制历史数量为 10
        self.history = self.history[:10]

    def update_current_history_progress(self):
        if not self.filepath: return
        for item in self.history:
            if item.get('path') == self.filepath:
                item['line_idx'] = self.current_line_idx
                break
        else:
            self.add_to_history()

    def load_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("Text/EPUB Files", "*.txt *.epub")])
        if not filepath:
            return

        self.update_current_history_progress() # 切换前保存现有的进度

        self.filepath = filepath
        self.process_file(self.filepath)
        self.current_line_idx = 0

        self.add_to_history()
        self.save_progress()
        self.update_display()

    def load_history_file(self, path):
        if not os.path.exists(path):
            messagebox.showwarning("提示", "文件已被移动或不存在")
            # 移除无效历史
            self.history = [item for item in self.history if item.get('path') != path]
            self.save_progress()
            return

        self.update_current_history_progress() # 切走前保存现有进度

        self.filepath = path
        # 寻找保留进度
        self.current_line_idx = 0
        for item in self.history:
            if item.get('path') == path:
                self.current_line_idx = item.get('line_idx', 0)
                break

        self.process_file(self.filepath)

        # 将刚刚加载的历史挪到最前
        self.add_to_history()
        self.save_progress()
        self.update_display()

    def process_file(self, filepath):
        self.content_lines = []
        try:
            if filepath.lower().endswith('.epub'):
                book = epub.read_epub(filepath)
                for item in book.get_items():
                    if item.get_type() == ebooklib.ITEM_DOCUMENT:
                        soup = BeautifulSoup(item.get_body_content(), 'html.parser')
                        text = soup.get_text(separator='\n')
                        lines = [line.strip() for line in text.split('\n') if line.strip()]
                        self.content_lines.extend(lines)
            else:
                 # TXT 处理
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        self.content_lines = [line.strip() for line in f.readlines() if line.strip()]
                except UnicodeDecodeError:
                    with open(filepath, 'r', encoding='gbk') as f:
                        self.content_lines = [line.strip() for line in f.readlines() if line.strip()]
        except Exception as e:
            messagebox.showerror("文件错误", f"无法解析该文件:\n{e}")

    def on_mouse_wheel(self, event):
        if event.delta < 0:
            self.turn_page(1)
        else:
            self.turn_page(-1)

    def turn_page(self, direction):
        if not self.content_lines: return

        if direction > 0:
            self.current_line_idx += self.lines_per_page
        else:
            self.current_line_idx -= self.lines_per_page

        if self.current_line_idx >= len(self.content_lines):
            self.current_line_idx = len(self.content_lines) - 1
        if self.current_line_idx < 0:
            self.current_line_idx = 0

        self.update_display()

    def update_display(self):
        if not self.content_lines:
             if self.filepath:
                  self._set_text(f"[已载入: {os.path.basename(self.filepath)}\n但未提取到有效文本]")
             return
        display_lines = self.content_lines[self.current_line_idx : self.current_line_idx + self.lines_per_page]
        text_to_show = "\n".join(display_lines)
        self._set_text(text_to_show)

    def change_alpha(self, delta):
        self.alpha += delta
        if self.alpha > 1.0: self.alpha = 1.0
        if self.alpha < 0.1: self.alpha = 0.1
        self.root.attributes("-alpha", self.alpha)

    def change_lines(self, delta):
        self.lines_per_page += delta
        if self.lines_per_page < 1: self.lines_per_page = 1
        self.update_display()

    def change_fg_color(self):
        color_code = colorchooser.askcolor(title="选择文字颜色")
        if color_code[1]:
            self.fg_color = color_code[1]
            self.text_widget.config(fg=self.fg_color)

    def quick_hide(self):
        self.root.withdraw()
        self.is_hidden = True

    def toggle_visibility(self):
        if self.is_hidden:
            self.root.deiconify()
            self.is_hidden = False
        else:
            self.root.withdraw()
            self.is_hidden = True

    # --- 进度持久化 JSON配置 ---
    def get_save_file(self):
        return os.path.join(os.path.expanduser("~"), ".moyu_reader_config.json")

    def save_progress(self):
        self.update_current_history_progress()

        data = {
            "filepath": self.filepath,
            "lines_per_page": self.lines_per_page,
            "alpha": self.alpha,
            "fg_color": self.fg_color,
            "hotkey": self.hotkey,
            "geometry": self.root.geometry(),
            "history": self.history
        }
        try:
            with open(self.get_save_file(), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception:
            pass

    def load_progress(self):
        save_file = self.get_save_file()
        if os.path.exists(save_file):
            try:
                with open(save_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                self.filepath = data.get("filepath", "")
                self.lines_per_page = data.get("lines_per_page", 3)
                self.alpha = float(data.get("alpha", 0.6))
                self.fg_color = data.get("fg_color", "#A9B7C6")
                self.hotkey = data.get("hotkey", "alt+shift+h")
                self.history = data.get("history", [])

                # 恢复外观属性
                self.root.attributes("-alpha", self.alpha)
                self.text_widget.config(fg=self.fg_color)
                geom = data.get("geometry", "")
                if geom: self.root.geometry(geom)

                if self.filepath and os.path.exists(self.filepath):
                    # 获取该文件的记录进度
                    for item in self.history:
                        if item.get('path') == self.filepath:
                            self.current_line_idx = item.get('line_idx', 0)
                            break
                    self.process_file(self.filepath)
            except Exception:
                pass

    def quit_app(self):
        self.save_progress()
        self.root.destroy()
        os._exit(0)

if __name__ == "__main__":
    root = tk.Tk()
    app = MoyuReader(root)
    root.mainloop()