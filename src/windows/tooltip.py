from tkinter import Label, Toplevel


class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.window = None
        self.after_id = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def _schedule(self, _event=None):
        self.hide()
        self.after_id = self.widget.after(500, self.show)

    def show(self):
        self.after_id = None
        if self.window is not None or not self.text:
            return
        self.widget.update_idletasks()
        x = self.widget.winfo_rootx() + self.widget.winfo_width() + 8
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        try:
            self.window = Toplevel(self.widget.winfo_toplevel())
            self.window.overrideredirect(True)
            self.window.attributes("-topmost", 1)
            self.window.geometry("+%d+%d" % (x, y))
            Label(self.window, text=self.text, justify="left", relief="solid", borderwidth=1, padding=6, wraplength=280).pack()
        except Exception:
            self.window = None

    def hide(self, _event=None):
        if self.after_id is not None:
            try:
                self.widget.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None
        if self.window is not None:
            try:
                self.window.destroy()
            except Exception:
                pass
            self.window = None
