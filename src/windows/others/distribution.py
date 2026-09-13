from tkinter import BOTTOM, LEFT, RIGHT, TOP, Canvas
from tkinter.ttk import Button, Frame, Label
from windows.popup import Popup

class DistributionDrawer(Popup):
    """
    Simple visual distribution editor.

    The user draws a curve:
        higher = delay happens more often
        lower = delay happens less often

    Distribution is stored as normalized points:

        [
            [0.0, 0.0],
            [0.1, 0.2],
            [0.2, 0.5],
            ...
            [1.0, 0.0]
        ]

    X is the position between Lower and Upper.
    Y is how common that value should be.
    """

    CANVAS_WIDTH = 600
    CANVAS_HEIGHT = 300
    SAMPLE_COUNT = 128

    def __init__(self, parent, main_app, lower_bound, upper_bound, distribution=None):
        text = main_app.text_content["options_menu"]["playback_menu"]["randomized_delay_settings"]
        super().__init__(main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["title"], 680, 470, parent)
        self.owner = parent
        self.main_app = main_app
        self.lower_bound = lower_bound
        self.upper_bound = upper_bound
        self.points = []
        Label(self, text=main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["sub_text"], font=("Segoe UI", 10)).pack(side=TOP, pady=(10, 8))

        graph_frame = Frame(self)
        graph_frame.pack(padx=15, pady=5)

        Label(graph_frame, text=main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["more_text"]).pack(side=TOP, pady=(0, 2))

        canvas_frame = Frame(graph_frame, relief="solid", borderwidth=1)
        canvas_frame.pack()

        self.canvas = Canvas(canvas_frame, width=self.CANVAS_WIDTH, height=self.CANVAS_HEIGHT, highlightthickness=0)
        self.canvas.pack()

        self._draw_grid()

        info_area = Frame(graph_frame)
        Label(info_area, text=self._format_number(lower_bound)).pack(side=LEFT, padx=(0, 250))
        Label(info_area, text=self._format_number(upper_bound)).pack(side=RIGHT, padx=(250, 0))
        info_area.pack(fill="x", pady=(4, 0))

        Label(graph_frame, text=main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["less_text"]).pack(side=TOP, pady=(2, 0))

        button_area = Frame(self)
        Button(button_area, text=main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["clear_text"], command=self.clear).pack(side=LEFT, padx=10)
        Button(button_area, text=main_app.text_content["global"]["confirm_button"], command=self.apply).pack(side=LEFT, padx=10)
        Button(button_area, text=main_app.text_content["global"]["cancel_button"], command=self.destroy).pack(side=LEFT, padx=10)
        button_area.pack(side=BOTTOM, pady=10)

        self.canvas.bind("<Button-1>", self.start_drawing)
        self.canvas.bind("<B1-Motion>", self.draw)
        self.canvas.bind("<ButtonRelease-1>", self.finish_drawing)
        # Draw the existing distribution, if one exists.
        self.load_distribution(distribution)
        self.update_idletasks()
        popup_width = min(max(680, self.winfo_reqwidth() + 10), 900)
        popup_height = min(max(470, self.winfo_reqheight() + 10), 700)
        self.geometry(f"{popup_width}x{popup_height}")
        self.wait_window()

    # def __init__(self, parent, main_app, lower_bound, upper_bound, distribution=None):
    #     text = main_app.text_content["options_menu"]["playback_menu"]["randomized_delay_settings"]
    #     super().__init__(main_app.text_content["options_menu"]["playback_menu"]["randomized_delay_settings"]["title"], 640, 430, parent)
    #     self.owner = parent
    #     self.main_app = main_app
    #     self.lower_bound = lower_bound
    #     self.upper_bound = upper_bound
    #     self.points = []
    #     Label(self, text=main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["title"], font=("Segoe UI", 10)).pack(side=TOP, pady=(10, 4))
    #     canvas_frame = Frame(self)
    #     self.canvas = Canvas(canvas_frame, width=self.CANVAS_WIDTH, height=self.CANVAS_HEIGHT, highlightthickness=1)
    #     self.canvas.pack()
    #     canvas_frame.pack(padx=10, pady=5)
    #     info_area = Frame(self)
    #     Label(info_area, text=main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["more_text"]).pack(side=TOP)
    #     Label(info_area, text=f"◄\t{self._format_number(lower_bound)}            |            {self._format_number(upper_bound)} ►").pack(side=TOP)
    #     Label(info_area, text=main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["less_text"]).pack(side=TOP)
    #     info_area.pack(pady=2)
    #     button_area = Frame(self)
    #     Button(button_area, text=main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["clear_text"], command=self.clear).pack(side=LEFT, padx=10)
    #     Button(button_area, text=main_app.text_content["global"]["confirm_button"], command=self.apply).pack(side=LEFT, padx=10)
    #     Button(button_area, text=main_app.text_content["global"]["cancel_button"], command=self.destroy).pack(side=LEFT, padx=10)
    #     button_area.pack(side=BOTTOM, pady=10)
    #     self.canvas.bind("<Button-1>", self.start_drawing)
    #     self.canvas.bind("<B1-Motion>", self.draw)
    #     self.canvas.bind("<ButtonRelease-1>", self.finish_drawing)
    #     # Draw the existing distribution, if one exists.
    #     self.load_distribution(distribution)
    #     self.update_idletasks()
    #     popup_width = min(max(640, self.winfo_reqwidth() + 10), 900)
    #     popup_height = min(max(430, self.winfo_reqheight() + 10), 700)
    #     self.geometry(f"{popup_width}x{popup_height}")
    #     self.wait_window()

    def start_drawing(self, event):
        self.points = [(self._canvas_to_normalized_x(event.x), self._canvas_to_normalized_y(event.y))]
        self.redraw()

    def draw(self, event):
        x = self._canvas_to_normalized_x(event.x)
        y = self._canvas_to_normalized_y(event.y)
        self.points.append((x, y))
        self.redraw()

    def finish_drawing(self, event):
        x = self._canvas_to_normalized_x(event.x)
        y = self._canvas_to_normalized_y(event.y)

        self.points.append((x, y))
        self.points = self._normalize_points(self.points)
        self.redraw()

    def _canvas_to_normalized_x(self, x):
        x = max(0, min(self.CANVAS_WIDTH, x))
        return x / self.CANVAS_WIDTH

    def _canvas_to_normalized_y(self, y):
        y = max(0, min(self.CANVAS_HEIGHT, y))
        return 1.0 - (y / self.CANVAS_HEIGHT)

    def _normalized_to_canvas(self, x, y):
        return (x * self.CANVAS_WIDTH, (1.0 - y) * self.CANVAS_HEIGHT)

    def _draw_grid(self):
        for x in range(0, self.CANVAS_WIDTH + 1, self.CANVAS_WIDTH // 10):
            self.canvas.create_line(x, 0, x, self.CANVAS_HEIGHT, fill="#d9d9d9", tags="grid")
        for y in range(0, self.CANVAS_HEIGHT + 1, self.CANVAS_HEIGHT // 10):
            self.canvas.create_line(0, y, self.CANVAS_WIDTH, y, fill="#d9d9d9", tags="grid")

    def _normalize_points(self, points):
        """
        Convert arbitrary mouse input into one point per X position.

        This means the saved distribution isn't tied to screen pixels.
        """
        if not points:
            return []
        cleaned = []
        for x, y in points:
            x = max(0.0, min(1.0, float(x)))
            y = max(0.0, min(1.0, float(y)))
            cleaned.append((x, y))
        cleaned.sort(key=lambda point: point[0])
        # Merge points that have effectively the same X.
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
        if len(self.points) < 1:
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

    def load_distribution(self, distribution):
        if not distribution:
            return
        try:
            points = []
            for point in distribution:
                if len(point) != 2:
                    continue
                x = float(point[0])
                y = float(point[1])
                x = max(0.0, min(1.0, x))
                y = max(0.0, min(1.0, y))
                points.append((x, y))
            self.points = self._normalize_points(points)
            self.redraw()
        except (TypeError, ValueError):
            self.points = []

    def clear(self):
        self.points = []
        self.canvas.delete("distribution")

    def apply(self):
        if not self.points:
            self.owner.distribution = None
            self.destroy()
            return
        distribution = self._resample_distribution()
        if not distribution:
            self.owner.distribution = None
        else:
            self.owner.distribution = distribution
        self.destroy()

    def _resample_distribution(self):
        """
        Convert the freehand line into a fixed number of evenly spaced
        points. This makes the saved data compact and predictable.
        """
        points = self._normalize_points(self.points)
        if len(points) < 2:
            return None
        result = []
        for index in range(self.SAMPLE_COUNT):
            x = index / (self.SAMPLE_COUNT - 1)
            y = self._interpolate(points, x)
            result.append([round(x, 6), round(max(0.0, min(1.0, y)), 6)])
        # If the entire drawing is at zero, there is no distribution.
        if max(point[1] for point in result) <= 0:
            return None
        return result

    @staticmethod
    def _interpolate(points, x):
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
