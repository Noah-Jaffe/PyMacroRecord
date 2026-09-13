import math
import tkinter as tk
from tkinter import BOTTOM, LEFT, RIGHT, TOP, Canvas
from tkinter.ttk import Button, Combobox, Frame, Label, Spinbox

from windows.popup import Popup


class DistributionDrawer(Popup):
    """
    Visual distribution editor.

    The curve is stored as normalized points:
        [x, y]

    X is the position between Lower and Upper.
    Y is how common / likely that value should be.

    Editing is non-destructive: drawing over an existing curve only replaces
    the portion of the curve covered by the new stroke. Right-click dragging
    erases the covered portion.
    """

    CANVAS_WIDTH = 600
    CANVAS_HEIGHT = 300
    DEFAULT_SAMPLE_COUNT = 128
    MIN_SAMPLE_COUNT = 1
    MAX_SAMPLE_COUNT = 4096
    EDIT_RADIUS_X = 0.012
    ERASE_RADIUS_X = 0.018

    PRESETS = {
        "Freehand": "freehand",
        "Linear": "linear",
        "Binomial": "binomial",
        "Logarithmic": "logarithmic",
        "Ex-Gaussian": "ex_gaussian",
    }

    def __init__(self, parent, main_app, lower_bound, upper_bound, distribution=None):
        self.owner = parent
        self.main_app = main_app
        self.lower_bound = lower_bound
        self.upper_bound = upper_bound
        self.points = []
        self._stroke = []
        self._editing = False
        self._erasing = False

        settings = main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]
        title = settings.get("title", "Distribution Editor")
        super().__init__(title, 900, 500, parent)

        Label(
            self,
            text=settings.get(
                "sub_text",
                "Draw the relative frequency of each value. Higher means more common.",
            ),
            font=("Segoe UI", 10),
        ).pack(side=TOP, pady=(10, 8))

        content = Frame(self)
        content.pack(fill="both", expand=True, padx=15, pady=(0, 5))

        graph_frame = Frame(content)
        graph_frame.pack(side=LEFT, fill="both", expand=True)

        Label(graph_frame, text="Higher frequency / more common").pack(side=TOP, pady=(0, 2))

        canvas_frame = Frame(graph_frame, relief="solid", borderwidth=1)
        canvas_frame.pack()

        self.canvas = Canvas(
            canvas_frame,
            width=self.CANVAS_WIDTH,
            height=self.CANVAS_HEIGHT,
            highlightthickness=0,
            cursor="crosshair",
        )
        self.canvas.pack()
        self._draw_grid()

        info_area = Frame(graph_frame)
        Label(info_area, text=f"Lower: {self._format_number(lower_bound)}").pack(side=LEFT)
        Label(info_area, text=f"Upper: {self._format_number(upper_bound)}").pack(side=RIGHT)
        info_area.pack(fill="x", pady=(4, 0))

        Label(graph_frame, text="Lower frequency / less common").pack(side=TOP, pady=(2, 0))
        Label(
            graph_frame,
            text="Left-drag to edit • Right-drag to erase",
            foreground="#666666",
        ).pack(side=TOP, pady=(6, 0))

        control_frame = Frame(content, relief="solid", borderwidth=1, padding=10)
        control_frame.pack(side=RIGHT, fill="y", padx=(15, 0))

        Label(control_frame, text="Curve controls", font=("Segoe UI", 10, "bold")).pack(
            anchor="w", pady=(0, 10)
        )

        Label(control_frame, text="Preset").pack(anchor="w")
        self.preset_var = tk.StringVar(value="Freehand")
        self.preset_box = Combobox(
            control_frame,
            textvariable=self.preset_var,
            values=list(self.PRESETS.keys()),
            state="readonly",
            width=18,
        )
        self.preset_box.pack(fill="x", pady=(2, 2))
        self.preset_box.bind("<<ComboboxSelected>>", self.apply_selected_preset)
        self._add_tooltip(
            self.preset_box,
            "Choose a common curve shape. Selecting a preset replaces the current curve.",
        )

        self.preset_description = Label(
            control_frame,
            text=self._preset_description("Freehand"),
            wraplength=180,
            justify="left",
            foreground="#555555",
        )
        self.preset_description.pack(anchor="w", pady=(0, 12))

        Label(control_frame, text="Number of samples / steps").pack(anchor="w")
        self.steps_var = tk.StringVar(value=str(self.DEFAULT_SAMPLE_COUNT))
        self.steps_spinbox = Spinbox(
            control_frame,
            from_=self.MIN_SAMPLE_COUNT,
            to=self.MAX_SAMPLE_COUNT,
            increment=1,
            textvariable=self.steps_var,
            width=10,
            validate="key",
            validatecommand=(self.register(self._validate_steps), "%P"),
        )
        self.steps_spinbox.pack(anchor="w", pady=(2, 2))
        self._add_tooltip(
            self.steps_spinbox,
            "Controls how many evenly spaced points are saved when you apply the curve (1–4096).",
        )

        Button(
            control_frame,
            text="Interpolate missing values",
            command=self.interpolate_missing,
        ).pack(fill="x", pady=(10, 4))
        self._add_tooltip(
            control_frame.winfo_children()[-1],
            "Fills gaps in the current drawing using straight-line interpolation and immediately redraws it.",
        )

        Button(control_frame, text="Clear drawing", command=self.clear).pack(fill="x", pady=4)
        self._add_tooltip(
            control_frame.winfo_children()[-1],
            "Remove the entire curve. This is separate from right-drag erasing, which only removes a selected area.",
        )

        # The bottom row is intentionally reserved for the popup actions only.
        bottom_frame = Frame(self)
        bottom_frame.pack(side=BOTTOM, fill="x", pady=(5, 10))
        Button(
            bottom_frame,
            text=main_app.text_content["global"].get("cancel_button", "Cancel"),
            command=self.destroy,
        ).pack(side=RIGHT, padx=(5, 15))
        Button(
            bottom_frame,
            text=main_app.text_content["global"].get("confirm_button", "Apply"),
            command=self.apply,
        ).pack(side=RIGHT, padx=5)

        self.canvas.bind("<Button-1>", self.start_drawing)
        self.canvas.bind("<B1-Motion>", self.draw)
        self.canvas.bind("<ButtonRelease-1>", self.finish_drawing)
        self.canvas.bind("<Button-3>", self.start_erasing)
        self.canvas.bind("<B3-Motion>", self.erase)
        self.canvas.bind("<ButtonRelease-3>", self.finish_erasing)

        self.load_distribution(distribution)

        self.update_idletasks()
        popup_width = min(max(900, self.winfo_reqwidth() + 10), 1100)
        popup_height = min(max(500, self.winfo_reqheight() + 10), 760)
        self.geometry(f"{popup_width}x{popup_height}")
        self.wait_window()

    def _validate_steps(self, value):
        if value == "":
            return True
        try:
            return self.MIN_SAMPLE_COUNT <= int(value) <= self.MAX_SAMPLE_COUNT
        except ValueError:
            return False

    def _get_sample_count(self):
        try:
            value = int(self.steps_var.get())
        except ValueError:
            value = self.DEFAULT_SAMPLE_COUNT
        return max(self.MIN_SAMPLE_COUNT, min(self.MAX_SAMPLE_COUNT, value))

    def _add_tooltip(self, widget, text):
        tooltip = {"window": None}

        def show(_event=None):
            if tooltip["window"] is not None:
                return
            x = widget.winfo_rootx() + 10
            y = widget.winfo_rooty() + widget.winfo_height() + 4
            window = tk.Toplevel(widget)
            window.wm_overrideredirect(True)
            window.geometry(f"+{x}+{y}")
            Label(
                window,
                text=text,
                justify="left",
                wraplength=260,
                relief="solid",
                borderwidth=1,
                padding=6,
            ).pack()
            tooltip["window"] = window

        def hide(_event=None):
            if tooltip["window"] is not None:
                tooltip["window"].destroy()
                tooltip["window"] = None

        widget.bind("<Enter>", show, add="+")
        widget.bind("<Leave>", hide, add="+")

    def _preset_description(self, name):
        descriptions = {
            "Freehand": "Draw any shape manually. Existing curve sections outside your stroke are preserved.",
            "Linear": "A straight ramp from low frequency to high frequency across the range.",
            "Binomial": "A bell-like discrete distribution, useful when outcomes cluster around a central value.",
            "Logarithmic": "Changes quickly near the low end and more gradually toward the high end.",
            "Ex-Gaussian": "A Gaussian-shaped peak with a longer tail, useful for skewed timing-like data.",
        }
        return descriptions.get(name, descriptions["Freehand"])

    def start_drawing(self, event):
        self._editing = True
        self._erasing = False
        self._stroke = [
            (self._canvas_to_normalized_x(event.x), self._canvas_to_normalized_y(event.y))
        ]
        self.redraw()

    def draw(self, event):
        if not self._editing or self._erasing:
            return
        self._stroke.append(
            (self._canvas_to_normalized_x(event.x), self._canvas_to_normalized_y(event.y))
        )
        self._merge_stroke_into_curve()
        self.redraw()

    def finish_drawing(self, event):
        if not self._editing or self._erasing:
            return
        self._stroke.append(
            (self._canvas_to_normalized_x(event.x), self._canvas_to_normalized_y(event.y))
        )
        self._merge_stroke_into_curve()
        self._stroke = []
        self._editing = False
        self.points = self._normalize_points(self.points)
        self.redraw()

    def start_erasing(self, event):
        self._editing = True
        self._erasing = True
        self._erase_at(event.x, event.y)
        self.redraw()

    def erase(self, event):
        if not self._editing or not self._erasing:
            return
        self._erase_at(event.x, event.y)
        self.redraw()

    def finish_erasing(self, _event):
        self._stroke = []
        self._editing = False
        self._erasing = False
        self.points = self._normalize_points(self.points)
        self.redraw()

    def _merge_stroke_into_curve(self):
        if not self._stroke:
            return
        stroke = self._normalize_points(self._stroke)
        if not stroke:
            return
        stroke_min = stroke[0][0]
        stroke_max = stroke[-1][0]

        if not self.points:
            self.points = stroke
            return

        left_y = self._interpolate(self.points, stroke_min)
        right_y = self._interpolate(self.points, stroke_max)
        merged = [(x, y) for x, y in self.points if x < stroke_min or x > stroke_max]

        if stroke_min > 0 and not any(abs(x - stroke_min) < 1e-6 for x, _ in merged):
            merged.append((stroke_min, left_y))
        if stroke_max < 1 and not any(abs(x - stroke_max) < 1e-6 for x, _ in merged):
            merged.append((stroke_max, right_y))

        merged.extend(stroke)
        self.points = self._normalize_points(merged)

    def _erase_at(self, canvas_x, canvas_y):
        x = self._canvas_to_normalized_x(canvas_x)
        y = self._canvas_to_normalized_y(canvas_y)
        remaining = []
        for px, py in self.points:
            x_distance = abs(px - x)
            y_distance = abs(py - y)
            if x_distance > self.ERASE_RADIUS_X or y_distance > 0.08:
                remaining.append((px, py))
        self.points = remaining

    def _canvas_to_normalized_x(self, x):
        x = max(0, min(self.CANVAS_WIDTH, x))
        return x / self.CANVAS_WIDTH

    def _canvas_to_normalized_y(self, y):
        y = max(0, min(self.CANVAS_HEIGHT, y))
        return 1.0 - (y / self.CANVAS_HEIGHT)

    def _normalized_to_canvas(self, x, y):
        return (x * self.CANVAS_WIDTH, (1.0 - y) * self.CANVAS_HEIGHT)

    def _draw_grid(self):
        self.canvas.delete("grid")
        for x in range(0, self.CANVAS_WIDTH + 1, self.CANVAS_WIDTH // 10):
            self.canvas.create_line(x, 0, x, self.CANVAS_HEIGHT, fill="#d9d9d9", tags="grid")
        for y in range(0, self.CANVAS_HEIGHT + 1, self.CANVAS_HEIGHT // 10):
            self.canvas.create_line(0, y, self.CANVAS_WIDTH, y, fill="#d9d9d9", tags="grid")

    def _normalize_points(self, points):
        if not points:
            return []
        cleaned = []
        for x, y in points:
            x = max(0.0, min(1.0, float(x)))
            y = max(0.0, min(1.0, float(y)))
            cleaned.append((x, y))
        cleaned.sort(key=lambda point: point[0])
        merged = []
        for x, y in cleaned:
            if merged and abs(merged[-1][0] - x) < 0.002:
                old_x, old_y = merged[-1]
                merged[-1] = ((old_x + x) / 2, (old_y + y) / 2)
            else:
                merged.append((x, y))
        return merged

    def redraw(self):
        self.canvas.delete("distribution")
        if not self.points:
            return
        coords = []
        for x, y in self.points:
            canvas_x, canvas_y = self._normalized_to_canvas(x, y)
            coords.extend((canvas_x, canvas_y))
        if len(coords) >= 4:
            self.canvas.create_line(*coords, width=3, smooth=True, tags="distribution")
        else:
            x, y = self._normalized_to_canvas(self.points[0][0], self.points[0][1])
            self.canvas.create_oval(x - 2, y - 2, x + 2, y + 2, tags="distribution")

        # Keep a live preview of the current stroke while drawing.
        if len(self._stroke) >= 2:
            stroke_coords = []
            for x, y in self._stroke:
                stroke_coords.extend(self._normalized_to_canvas(x, y))
            self.canvas.create_line(*stroke_coords, width=3, dash=(5, 3), tags="distribution")

    def load_distribution(self, distribution):
        if not distribution:
            return
        try:
            points = []
            for point in distribution:
                if len(point) != 2:
                    continue
                x = max(0.0, min(1.0, float(point[0])))
                y = max(0.0, min(1.0, float(point[1])))
                points.append((x, y))
            self.points = self._normalize_points(points)
            self.redraw()
        except (TypeError, ValueError):
            self.points = []

    def clear(self):
        self.points = []
        self._stroke = []
        self.redraw()

    def apply_selected_preset(self, _event=None):
        name = self.preset_var.get()
        self.preset_description.config(text=self._preset_description(name))
        if name == "Freehand":
            return
        self.points = self._make_preset(self.PRESETS[name], self._get_sample_count())
        self._stroke = []
        self.redraw()

    def _make_preset(self, preset, sample_count):
        if sample_count <= 1:
            sample_count = 2
        raw = []
        for index in range(sample_count):
            x = index / (sample_count - 1)
            if preset == "linear":
                y = x
            elif preset == "binomial":
                # Symmetric binomial PMF sampled across a continuous x range.
                n = 12
                k = round(n * x)
                pmf = math.comb(n, k) * (0.5 ** n)
                y = pmf
            elif preset == "logarithmic":
                y = math.log1p(9.0 * x) / math.log(10.0)
            elif preset == "ex_gaussian":
                y = self._ex_gaussian_pdf(x, mu=0.42, sigma=0.13, rate=5.5)
            else:
                y = 0.0
            raw.append((x, y))

        max_y = max(y for _, y in raw) if raw else 0.0
        if max_y > 0:
            raw = [(x, y / max_y) for x, y in raw]
        return raw

    @staticmethod
    def _ex_gaussian_pdf(x, mu, sigma, rate):
        value = (rate / 2.0) * math.exp(
            rate * (mu - x) + (rate * rate * sigma * sigma) / 2.0
        ) * math.erfc(
            (mu + (rate * sigma * sigma) - x) / (math.sqrt(2.0) * sigma)
        )
        return max(0.0, value)

    def interpolate_missing(self):
        """
        Make the current drawing continuous at the selected number of steps.
        The interpolated values replace the visible drawing immediately.
        """
        if len(self.points) < 2:
            return

        sample_count = self._get_sample_count()
        result = []
        for index in range(sample_count):
            x = index / (sample_count - 1) if sample_count > 1 else 0.0
            y = self._interpolate(self.points, x)
            result.append((x, max(0.0, min(1.0, y))))
        self.points = result
        self.redraw()

    def apply(self):
        if not self.points:
            self.owner.distribution = None
            self.destroy()
            return

        distribution = self._resample_distribution()
        self.owner.distribution = distribution
        self.destroy()

    def _resample_distribution(self):
        points = self._normalize_points(self.points)
        if len(points) < 2:
            return None

        sample_count = self._get_sample_count()
        result = []
        for index in range(sample_count):
            x = index / (sample_count - 1) if sample_count > 1 else 0.0
            y = self._interpolate(points, x)
            result.append([round(x, 6), round(max(0.0, min(1.0, y)), 6)])

        if max(point[1] for point in result) <= 0:
            return None
        return result

    @staticmethod
    def _interpolate(points, x):
        if not points:
            return 0.0
        if len(points) == 1:
            return points[0][1]
        if x <= points[0][0]:
            return points[0][1]
        if x >= points[-1][0]:
            return points[-1][1]
        for index in range(1, len(points)):
            x1, y1 = points[index - 1]
            x2, y2 = points[index]
            if x <= x2:
                if x2 == x1:
                    return y2
                amount = (x - x1) / (x2 - x1)
                return y1 + ((y2 - y1) * amount)
        return points[-1][1]

    @staticmethod
    def _format_number(value):
        if float(value).is_integer():
            return str(int(value))
        return str(value)
