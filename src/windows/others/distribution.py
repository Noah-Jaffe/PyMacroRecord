import math
from tkinter import BOTTOM, LEFT, TOP, Canvas, Frame as TkFrame, Scrollbar, StringVar
from tkinter import messagebox
from tkinter.ttk import Button, Combobox, Entry, Frame, Label, Separator

from windows.popup import Popup
from windows.tooltip import Tooltip


class DistributionDrawer(Popup):
    """
    The curve is stored as normalized points:
        [x, y]

    X is the position between Lower and Upper.
    Y is how common / likely that value should be.

    Drawing is non-destructive: drawing over an existing curve only replaces
    the portion covered by the new stroke. Right-click dragging erases the
    covered portion. Green points are individually draggable vertically.
    """

    CANVAS_WIDTH = 560 # @TODO: Shouldn't this be percentages of the avaiable window size?
    CANVAS_HEIGHT = 280 # @TODO: Shouldn't this be percentages of the avaiable window size?
    CONTROL_WIDTH = 270 # @TODO: Shouldn't this be percentages of the avaiable window size?
    MIN_WIDTH = 760
    MIN_HEIGHT = 500
    INITIAL_WIDTH = 980
    INITIAL_HEIGHT = 620

    NORMALIZE_X_THRESHOLD = 0.002
    POINT_HIT_RADIUS_PX = 9
    ERASE_X_THRESHOLD = 0.018
    ERASE_Y_THRESHOLD = 0.08
    ZOOM_FACTOR = 1.25
    MIN_VIEW_SPAN = 0.05
    MAX_GENERATED_SAMPLES = 256 # @TODO: can we remove the use of preset point locations so that zoom will work smoother or is this value purely for what is displayed on the graph?
    MAX_PEAKS = 100 # @TODO: is the max peaks a requirement? can we uncap this?

    POINT_COLOR = "#4a890b"
    LINE_COLOR = "#4a0b89"
    GRID_COLOR = "#d9d9d9"
    ZERO_VERTICAL_AXIS_MARK_COLOR = "#9f9f9f"
    BASELINE_COLOR = "#8c8c8c"
    AXIS_TEXT_COLOR = "#555555"
    STROKE_COLOR = "#4a890b9f"

    PRESET_KEYS = ("freehand", "linear", "curve_generation")
    INTERPOLATION_KEYS = ("sharp", "curves")
    TAIL_SIDE_KEYS = ("both", "left", "right")

    CURVE_CONTROLS_DEFAULTS = {
        "center": 50,
        "width": 20,
        "height": 100,
        "tail": 0,
        "asymmetry": 0,
        "tail_side": TAIL_SIDE_KEYS[0],
        "peaks": 1,
    }
    
    def __init__(self, parent, main_app, lower_bound, upper_bound, distribution=None):
        self.owner = parent
        self.main_app = main_app
        self.lower_bound = lower_bound
        self.upper_bound = upper_bound
        self.points = []
        self.user_points = []
        self.stroke = []
        self.editing = False
        self.erasing = False
        self.dragging_point = False
        self.dragged_user_index = None
        self.dragged_user_point = None
        self.preset = "freehand"
        self.interpolation_mode = "curves"
        self.view_x_min = 0.0
        self.view_x_max = 1.0
        self.view_y_min = 0.0
        self.view_y_max = 1.0
        self.graph_width = self.CANVAS_WIDTH
        self.graph_height = self.CANVAS_HEIGHT
        self._scroll_update_scheduled = False
        self._previous_prevent_record = getattr(main_app, "prevent_record", None)
        self._modal_state_restored = False
        self._peak_rows = []
        self._peak_rebuild_pending = False

        super().__init__(self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["title"], self.INITIAL_WIDTH, self.INITIAL_HEIGHT, parent)
        self.resizable(True, True)
        self.minsize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.maxsize(self.winfo_screenwidth(), self.winfo_screenheight())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self._set_modal_input_prevention(True) # @TODO: explain the rationale for using this method rather than just calling `self.main_app.prevent_record = True`

        try:
            self._initialize_variables()
            self._build_ui()
            self.load_distribution(distribution)
            self._apply_initial_state()
            self._update_graph_size()
            self._redraw()
            self.wait_window()
        finally:
            self._restore_modal_input_prevention() # @TODO: explain the rationale for using this method rather than just calling `self.main_app.prevent_record = False`
        
    def _initialize_variables(self):
        self.preset_var = StringVar(value=self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["presets"]["freehand"]["label_text"])
        self.interpolation_var = StringVar(value=self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["settings_information"]["interpolation_types"]["curves_text"])
        self._reset_generator(set_active_preset_to_generator=False)

    def _build_ui(self):
        """Build all ui elements for this popup window."""
        Label(self, text=self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["distribution_instruction_text"], font=("Segoe UI", 10), justify="left", anchor="w").pack(side=TOP, fill="x", padx=15, pady=(10, 8))
        content = Frame(self)
        content.pack(fill="both", expand=True, padx=15, pady=(0, 4))
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        self._build_graph(content)
        self._build_settings_panel(content)
        self._build_action_bar()

    def _build_graph(self, parent):
        graph_frame = Frame(parent)
        graph_frame.grid(row=0, column=0, sticky="nsew")
        graph_frame.rowconfigure(1, weight=1)
        graph_frame.columnconfigure(1, weight=1)
        high_label = Label(graph_frame, text=self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["axis_information"]["vertical"]["high_text"])
        high_label.grid(row=0, column=1, sticky="w", pady=(0, 2))
        Tooltip(high_label, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["axis_information"]["vertical"]["tooltip_text"])

        canvas_frame = Frame(graph_frame, relief="solid", borderwidth=1)
        canvas_frame.grid(row=1, column=1, sticky="nsew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        self.canvas = Canvas(canvas_frame, width=self.CANVAS_WIDTH, height=self.CANVAS_HEIGHT, highlightthickness=0, cursor="crosshair")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Button-1>", self._on_physical_press)
        self.canvas.bind("<Button-3>", self._on_physical_press)
        self.canvas.bind("<B1-Motion>", self._on_physical_motion)
        self.canvas.bind("<B3-Motion>", self._on_physical_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_physical_release)
        self.canvas.bind("<ButtonRelease-3>", self._on_physical_release)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel_zoom, add="+")
        self.canvas.bind("<Button-4>", self._on_mousewheel_zoom, add="+")
        self.canvas.bind("<Button-5>", self._on_mousewheel_zoom, add="+")

        info_area = Frame(graph_frame)
        info_area.grid(row=2, column=1, sticky="ew", pady=(4, 0))
        info_area.columnconfigure(0, weight=1)
        info_area.columnconfigure(1, weight=1)
        info_area.columnconfigure(2, weight=1)
        info_area.columnconfigure(3, weight=1)
        info_area.columnconfigure(4, weight=1)
        self.axis_percent_labels = []
        for index in range(5):
            label = Label(info_area, text="", foreground=self.AXIS_TEXT_COLOR)
            label.grid(row=0, column=index, sticky="ew")
            self.axis_percent_labels.append(label)

        bounds_area = Frame(graph_frame)
        bounds_area.grid(row=3, column=1, sticky="ew")
        bounds_area.columnconfigure(0, weight=1)
        bounds_area.columnconfigure(1, weight=1)
        self.lower_bound_label = Label(bounds_area, text=f'{self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["axis_information"]["horizontal"]["low_value_text" ]}: {self._format_number(self.lower_bound)}', anchor="w")
        self.lower_bound_label.grid(row=0, column=0, sticky="w")
        self.upper_bound_label = Label(bounds_area, text=f'{self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["axis_information"]["horizontal"]["high_value_text"]}: {self._format_number(self.upper_bound)}', anchor="e")
        self.upper_bound_label.grid(row=0, column=1, sticky="e")
        Tooltip(bounds_area, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["axis_information"]["horizontal"]["tooltip_text"])

        low_label = Label(graph_frame, text=self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["axis_information"]["vertical"]["low_text"])
        low_label.grid(row=4, column=1, sticky="w", pady=(2, 0))
        Label(graph_frame, text=self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["help_instructions_text"], foreground="#666666", justify="left", wraplength=560).grid(row=5, column=1, sticky="w", pady=(6, 0))

    def _build_settings_panel(self, parent):
        panel = Frame(parent, relief="solid", borderwidth=1)
        panel.grid(row=0, column=1, sticky="nsew", padx=(15, 0))
        panel.rowconfigure(0, weight=1)
        panel.columnconfigure(0, weight=1)

        self.control_canvas = Canvas(panel, width=self.CONTROL_WIDTH, highlightthickness=0, borderwidth=0)
        self.control_scrollbar = Scrollbar(panel, orient="vertical", command=self.control_canvas.yview)
        self.control_canvas.configure(yscrollcommand=self.control_scrollbar.set)
        self.control_canvas.grid(row=0, column=0, sticky="nsew")
        self.control_scrollbar.grid(row=0, column=1, sticky="ns")

        self.controls_inner = Frame(self.control_canvas, padding=10)
        self.controls_window = self.control_canvas.create_window((0, 0), window=self.controls_inner, anchor="nw")
        self.controls_inner.bind("<Configure>", self._update_controls_scroll_region)
        self.control_canvas.bind("<Configure>", self._resize_controls_inner)
        self._bind_control_scroll(self.control_canvas)

        self._add_section_header(self.controls_inner, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["settings_information"]["header_text"])
        preset_section = Frame(self.controls_inner)
        preset_section.pack(fill="x", pady=(0, 10))
        Label(preset_section, text=self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["settings_information"]["preset_text"]).pack(anchor="w")
        Tooltip(preset_section, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["settings_information"]["preset_tooltip_text"])
        preset_labels = {
            k: self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["presets"][k]["label_text"]
            for k in self.PRESET_KEYS
        }
        self._preset_key_by_label = {label: key for key, label in preset_labels.items()}
        self._preset_label_by_key = preset_labels
        self.preset_box = Combobox(preset_section, textvariable=self.preset_var, values=list(preset_labels.values()), state="readonly", width=22)
        self.preset_box.pack(fill="x", pady=(2, 2))
        self.preset_box.bind("<<ComboboxSelected>>", self._on_preset_changed)
        self.preset_description = Label(preset_section, text=self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["presets"]["freehand"]["description_text"], foreground="#555555", justify="left", wraplength=220)
        self.preset_description.pack(anchor="w", pady=(2, 2))
        self.preset_note = Label(preset_section, text=self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["presets"]["freehand"]["note_text"], foreground="#555555", justify="left", wraplength=220)
        self.preset_note.pack(anchor="w")

        self.curve_generation_frame = Frame(self.controls_inner)
        self._build_curve_generation_controls(self.curve_generation_frame)

        Separator(self.controls_inner, orient="horizontal").pack(fill="x", pady=6)
        interpolation_section = Frame(self.controls_inner)
        interpolation_section.pack(fill="x", pady=(0, 10))
        Label(interpolation_section, text=self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["settings_information"]["interpolate_text"]).pack(anchor="w")
        Tooltip(interpolation_section, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["settings_information"]["interpolate_tooltip_text"])
        interpolation_labels = {
            k: self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["settings_information"]["interpolation_types"][f"{k}_text"]
            for k in self.INTERPOLATION_KEYS
        }
        self._interpolation_key_by_label = {label: key for key, label in interpolation_labels.items()}
        self._interpolation_label_by_key = interpolation_labels
        self.interpolation_box = Combobox(interpolation_section, textvariable=self.interpolation_var, values=list(interpolation_labels.values()), state="readonly", width=22)
        self.interpolation_box.pack(fill="x", pady=(2, 2))
        self.interpolation_box.bind("<<ComboboxSelected>>", self._on_interpolation_changed)
        interpolate_button = Button(interpolation_section, text=self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["settings_information"]["interpolate_button_text"], command=self.interpolate_missing)
        interpolate_button.pack(fill="x", pady=(6, 2))
        Tooltip(interpolate_button, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["settings_information"]["interpolate_button_tooltip_text"])

        self._build_editing_controls(self.controls_inner)
        self._build_zoom_controls(self.controls_inner)
        self.after_idle(self._update_controls_scroll_state)

    def _build_curve_generation_controls(self, parent):
        self._add_section_header(parent, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["header_text"])
        self._add_numeric_entry(parent, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["center_text"], self.generator_center_var, 0.0, 100.0, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["center_tooltip_text"], "float")
        self._add_numeric_entry(parent, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["width_text"], self.generator_width_var, 0.5, 100.0, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["width_tooltip_text"], "float")
        self._add_numeric_entry(parent, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["height_text"], self.generator_height_var, 0.0, 100.0, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["height_tooltip_text"], "float")
        self._add_numeric_entry(parent, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["tail_text"]  , self.generator_tail_var  , 0.0, 100.0, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["tail_tooltip_text"],   "float")
        Label(parent, text=self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["tail_side_text"]).pack(anchor="w", pady=(3, 1))
        tail_labels = {
            k: self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"][f"tail_side_{k}_text"]
            for k in self.TAIL_SIDE_KEYS
        }
        self._tail_side_key_by_label = {label: key for key, label in tail_labels.items()}
        self.tail_side_box = Combobox(parent, textvariable=self.generator_tail_side_var, values=list(tail_labels.values()), state="readonly", width=22)
        self.tail_side_box.pack(fill="x", pady=(0, 3))
        self._add_numeric_entry(parent, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["asymmetry_text"], self.generator_asymmetry_var, -100.0, 100.0, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["asymmetry_tooltip_text"], "float")

        Label(parent, text=self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["peaks_text"]).pack(anchor="w", pady=(3, 1))
        Tooltip(parent, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["peaks_tooltip_text"])
        self.peaks_spinbox = Entry(parent, textvariable=self.generator_peaks_var, width=22, validate="key", validatecommand=(self.main_app.validate_cmd_int, "%d", "%P"))
        self.peaks_spinbox.pack(fill="x", pady=(0, 3))
        self.generator_peaks_var.trace_add("write", self._schedule_peak_rebuild)
        self.peak_controls_frame = Frame(parent)
        self.peak_controls_frame.pack(fill="x", pady=(3, 5))
        self._rebuild_peak_controls()

        generate_button = Button(parent, text=self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["generate_text"], command=self._generate_button)
        generate_button.pack(fill="x", pady=(4, 3))
        Tooltip(generate_button, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["generate_tooltip_text"])
        reset_button = Button(parent, text=self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["reset_text"], command=self._reset_generator)
        reset_button.pack(fill="x", pady=(0, 8))
        Tooltip(reset_button, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["reset_tooltip_text"])

    def _build_editing_controls(self, parent):
        self._add_section_header(parent, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["editing"]["header_text"])
        info = Label(parent, text=self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["help_instructions_text"], foreground="#555555", justify="left", wraplength=220)
        info.pack(fill="x", pady=(0, 5))
        Tooltip(info, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["editing"]["draw_text"] + ": " + self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["axis_information"]["horizontal"]["tooltip_text"] + "\n" + self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["editing"]["erase_text"])
        clear_button = Button(parent, text=self.main_app.text_content["global"]["clear_button"], command=self.clear)
        clear_button.pack(fill="x", pady=(0, 8))
        Tooltip(clear_button, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["settings_information"]["clear_tooltip_text"])

    def _build_zoom_controls(self, parent):
        self._add_section_header(parent, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["settings_information"]["zoom_text"])
        zoom_frame = Frame(parent)
        zoom_frame.pack(fill="x", pady=(0, 8))
        Button(zoom_frame, text=self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["settings_information"]["zoom_in_text"], command=self._zoom_in).pack(fill="x", pady=2)
        Button(zoom_frame, text=self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["settings_information"]["zoom_out_text"], command=self._zoom_out).pack(fill="x", pady=2)
        Button(zoom_frame, text=self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["settings_information"]["zoom_reset_text"], command=self._reset_zoom).pack(fill="x", pady=2)
        Tooltip(zoom_frame, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["settings_information"]["zoom_tooltip_text"])

    def _build_action_bar(self):
        action_bar = Frame(self)
        action_bar.pack(side=BOTTOM, pady=8)
        Button(action_bar, text=self.main_app.text_content["global"]["apply_button"], command=self.apply).pack(side=LEFT, padx=5)
        Button(action_bar, text=self.main_app.text_content["global"]["cancel_button"], command=self.cancel).pack(side=LEFT, padx=5)

    def _add_section_header(self, parent, text):
        Label(parent, text=text, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 6))

    def _add_numeric_entry(self, parent, label_text, variable, minimum, maximum, tooltip_text=None, kind="float"):
        label = Label(parent, text=label_text)
        label.pack(anchor="w", pady=(3, 1))
        if tooltip_text:
            Tooltip(label, tooltip_text)
        entry = Entry(parent, textvariable=variable, width=22, validate="key", validatecommand=(self.main_app.validate_cmd_int if kind == 'int' else self.main_app.validate_cmd_float, "%d", "%P"))
        entry.pack(fill="x", pady=(0, 1))
        entry.bind("<FocusOut>", lambda _event, var=variable, low=minimum, high=maximum: self._clamp_variable(var, low, high), add="+")
        return entry


    def _bind_control_scroll(self, widget):
        widget.bind("<MouseWheel>", self._scroll_controls, add="+")
        widget.bind("<Button-4>", self._scroll_controls_up, add="+")
        widget.bind("<Button-5>", self._scroll_controls_down, add="+")
        if isinstance(widget, (TkFrame, Frame, Canvas)):
            for child in widget.winfo_children():
                self._bind_control_scroll(child)

    def _update_controls_scroll_region(self, _event=None):
        self.control_canvas.configure(scrollregion=self.control_canvas.bbox("all"))
        self._schedule_scroll_state_update()

    def _resize_controls_inner(self, event):
        self.control_canvas.itemconfigure(self.controls_window, width=event.width)
        self._update_controls_scroll_region()

    def _schedule_scroll_state_update(self, *_args):
        if self._scroll_update_scheduled:
            return
        self._scroll_update_scheduled = True
        self.after_idle(self._update_controls_scroll_state)

    def _update_controls_scroll_state(self):
        self._scroll_update_scheduled = False
        bbox = self.control_canvas.bbox("all")
        if bbox is None:
            return
        if bbox[3] - bbox[1] <= self.control_canvas.winfo_height() + 1:
            self.control_canvas.yview_moveto(0)
            self.control_scrollbar.grid_remove()
        else:
            self.control_scrollbar.grid()

    def _has_control_scroll(self):
        bbox = self.control_canvas.bbox("all")
        return bbox is not None and (bbox[3] - bbox[1]) > self.control_canvas.winfo_height() + 1

    def _scroll_controls(self, event):
        if not self._has_control_scroll():
            return
        delta = getattr(event, "delta", 0)
        self.control_canvas.yview_scroll(int(-delta / 120) if delta else 0, "units")

    def _scroll_controls_up(self, _event=None):
        if self._has_control_scroll():
            self.control_canvas.yview_scroll(-1, "units")

    def _scroll_controls_down(self, _event=None):
        if self._has_control_scroll():
            self.control_canvas.yview_scroll(1, "units")

    def _on_canvas_configure(self, event):
        self.graph_width = max(1, event.width)
        self.graph_height = max(1, event.height)
        self._redraw()

    def _update_graph_size(self):
        self.update_idletasks()
        self.graph_width = max(1, self.canvas.winfo_width())
        self.graph_height = max(1, self.canvas.winfo_height())

    def _apply_initial_state(self):
        self.preset_var.set(self._preset_label_by_key["freehand"])
        self.interpolation_var.set(self._interpolation_label_by_key["curves"])
        self.preset = "freehand"
        self.interpolation_mode = "curves"
        self._update_preset_description("freehand")

    def _on_preset_changed(self, _event=None):
        key = self._selected_preset_key()
        self.preset = key
        self._update_preset_description(key)
        if key == "freehand":
            self.interpolation_mode = self.interpolation_mode
            self.interpolation_var.set(self._interpolation_label_by_key[self.interpolation_mode])
            self.curve_generation_frame.pack_forget()
            self._redraw()
            return
        if key == "linear":
            self.curve_generation_frame.pack_forget()
            self._apply_linear()
            self.interpolation_mode = "sharp"
            self.interpolation_var.set(self._interpolation_label_by_key["sharp"])
            self._redraw()
            return
        self.curve_generation_frame.pack(fill="x", pady=(0, 5))
        self.interpolation_mode = "curves"
        self.interpolation_var.set(self._interpolation_label_by_key["curves"])
        self._generate_curve()
        self._redraw()

    def _update_preset_description(self, key):
        self.preset_description.configure(text=self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["presets"][key]["description_text"])
        self.preset_note.configure(text=self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["presets"][key]["note_text"])

    def _selected_preset_key(self):
        return self._preset_key_by_label.get(self.preset_var.get(), "freehand")

    def _selected_interpolation_key(self):
        return self._interpolation_key_by_label.get(self.interpolation_var.get(), "curves")

    def _on_interpolation_changed(self, _event=None):
        self.interpolation_mode = self._selected_interpolation_key()
        self._redraw()

    def _schedule_peak_rebuild(self, *_args):
        if self._peak_rebuild_pending:
            return
        self._peak_rebuild_pending = True
        self.after_idle(self._rebuild_peak_controls)

    def _rebuild_peak_controls(self):
        self._peak_rebuild_pending = False
        if not hasattr(self, "peak_controls_frame"):
            return
        for child in self.peak_controls_frame.winfo_children():
            child.destroy()
        try:
            count = int(self.generator_peaks_var.get())
        except (TypeError, ValueError):
            count = 1
        count = max(0, min(self.MAX_PEAKS, count))
        self._peak_rows = []
        if count == 0:
            Label(self.peak_controls_frame, text=self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["empty_peaks_text"], foreground="#555555", justify="left", wraplength=220).pack(anchor="w")
            return
        Label(self.peak_controls_frame, text=self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["peak_controls_text"], font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        for index in range(count):
            defaults = self._default_peak_values(index, count)
            row = Frame(self.peak_controls_frame, relief="solid", borderwidth=1, padding=5)
            row.pack(fill="x", pady=3)
            Label(row, text="%s %d" % (self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["peaks_text"], index + 1), font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 3))
            center_var = StringVar(value=self._format_input_number(self.CURVE_CONTROLS_DEFAULTS["center"]))
            width_var = StringVar(value=self._format_input_number(self.CURVE_CONTROLS_DEFAULTS["width"]))
            height_var = StringVar(value=self._format_input_number(self.CURVE_CONTROLS_DEFAULTS["height"]))
            asymmetry_var = StringVar(value=self._format_input_number(self.CURVE_CONTROLS_DEFAULTS["asymmetry"]))
            self._add_peak_row_field(row, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["peak_center_text"], center_var, 0.0, 100.0, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["peak_tooltip_text"])
            self._add_peak_row_field(row, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["peak_width_text"], width_var, 0.5, 100.0, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["peak_tooltip_text"])
            self._add_peak_row_field(row, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["peak_height_text"], height_var, 0.0, 100.0, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["peak_tooltip_text"])
            self._add_peak_row_field(row, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["peak_asymmetry_text"], asymmetry_var, -100.0, 100.0, self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["peak_tooltip_text"])
            self._peak_rows.append({"center": center_var, "width": width_var, "height": height_var, "asymmetry": asymmetry_var})

    def _add_peak_row_field(self, parent, label_text, variable, minimum, maximum, tooltip):
        label = Label(parent, text=label_text)
        label.pack(anchor="w", pady=(1, 0))
        Tooltip(label, tooltip)
        entry = Entry(parent, textvariable=variable, width=20, validate="key", validatecommand=(self.main_app.validate_cmd_float, "%d", "%P"))
        entry.pack(fill="x", pady=(0, 1))
        entry.bind("<FocusOut>", lambda _event, var=variable, low=minimum, high=maximum: self._clamp_variable(var, low, high), add="+")

    def _default_peak_values(self, index, count):
        errors = []
        try:
            center = float(self.generator_center_var.get())
        except (TypeError, ValueError) as e:
            errors.append("center")
            center = float(self.CURVE_CONTROLS_DEFAULTS["center"])
        try:
            width = float(self.generator_width_var.get())
        except (TypeError, ValueError):
            errors.append("width")
            width = float(self.CURVE_CONTROLS_DEFAULTS["width"])
        try:
            height = float(self.generator_height_var.get())
        except (TypeError, ValueError):
            errors.append("height")
            height = float(self.CURVE_CONTROLS_DEFAULTS["height"])
        try:
            asymmetry = float(self.generator_asymmetry_var.get())
        except (TypeError, ValueError):
            errors.append("asymmetry")
            asymmetry = float(self.CURVE_CONTROLS_DEFAULTS["asymmetry"])
        
        if errors:
            error_message = self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"]["input_error_text"] + "\n".join(
                f"> {self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["curve_generation"][e+"_text"]}" for e in errors
            )
            # @TODO: should this be popup? Is this error list even needed?
            # messagebox.showerror(self.main_app.text_content["global"]["error"], error_message)
            print(error_message)

        if count <= 1:
            return center, width, height, asymmetry
        spacing = min(82.0, max(12.0, width * 4.0))
        start = max(0.0, center - spacing / 2.0)
        end = min(100.0, center + spacing / 2.0)
        actual_index = index / (count - 1)
        return start + (end - start) * actual_index, width, height, asymmetry

    def _generate_button(self):
        if self._selected_preset_key() != "curve_generation":
            self.preset_var.set(self._preset_label_by_key["curve_generation"])
            self.preset = "curve_generation"
            self._update_preset_description("curve_generation")
            self.curve_generation_frame.pack(fill="x", pady=(0, 5))
        if not self._validate_generator_inputs():
            self._show_generator_error()
            return
        self.interpolation_mode = "curves"
        self.interpolation_var.set(self._interpolation_label_by_key["curves"])
        self._generate_curve()
        self._redraw()

    def _reset_generator(self, set_active_preset_to_generator=True):
        """Reset the generator variables to the defaults

        Args:
            set_active_preset_to_generator (bool, optional): True if you want to force the active preset to be the curve generator as well, otherwise False. Defaults to True.
        """
        self.generator_center_var.set(str(self.CURVE_CONTROLS_DEFAULTS["center"]))
        self.generator_width_var.set(str(self.CURVE_CONTROLS_DEFAULTS["width"]))
        self.generator_height_var.set(str(self.CURVE_CONTROLS_DEFAULTS["height"]))
        self.generator_tail_var.set(str(self.CURVE_CONTROLS_DEFAULTS["tail"]))
        self.generator_asymmetry_var.set(str(self.CURVE_CONTROLS_DEFAULTS["asymmetry"]))
        self.generator_tail_side_var.set(self.CURVE_CONTROLS_DEFAULTS["tail_side"])
        self.generator_peaks_var.set(self.CURVE_CONTROLS_DEFAULTS["peaks"])
        if set_active_preset_to_generator:
            self.after_idle(self._rebuild_peak_controls)
            if self._selected_preset_key() != "curve_generation":
                self.preset_var.set(self._preset_label_by_key["curve_generation"])
                self.preset = "curve_generation"
                self._update_preset_description("curve_generation")
                self.curve_generation_frame.pack(fill="x", pady=(0, 5))
            self.interpolation_mode = "curves"
            self.interpolation_var.set(self._interpolation_label_by_key["curves"])


    def _validate_generator_inputs(self):
        fields = (
            (self.generator_center_var, 0.0, 100.0),
            (self.generator_width_var, 0.5, 100.0),
            (self.generator_height_var, 0.0, 100.0),
            (self.generator_tail_var, 0.0, 100.0),
            (self.generator_asymmetry_var, -100.0, 100.0)
        )
        for variable, minimum, maximum in fields:
            value = self._finite_float(variable.get())
            if value is None or value < minimum or value > maximum:
                return False
        count = self._safe_int(self.generator_peaks_var.get(), None)
        if count is None or count < 0 or count > self.MAX_PEAKS:
            return False
        for row in self._peak_rows:
            for key, minimum, maximum in (("center", 0.0, 100.0), ("width", 0.5, 100.0), ("height", 0.0, 100.0), ("asymmetry", -100.0, 100.0)):
                value = self._finite_float(row[key].get())
                if value is None or value < minimum or value > maximum:
                    return False
        return True

    def _show_generator_error(self):
        self._safe_messagebox("showerror", self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["error"]["invalid_generator_text"])

    def _generate_curve(self):
        if not self._validate_generator_inputs():
            return False
        try:
            center = float(self.generator_center_var.get()) / 100.0
            width = max(0.005, float(self.generator_width_var.get()) / 100.0)
            height = max(0.0, float(self.generator_height_var.get()) / 100.0)
            tail = max(0.0, min(1.0, float(self.generator_tail_var.get()) / 100.0))
            asymmetry = max(-1.0, min(1.0, float(self.generator_asymmetry_var.get()) / 100.0))
            peak_specs = []
            for row in self._peak_rows:
                peak_specs.append({
                    "center": float(row["center"].get()) / 100.0,
                    "width": max(0.005, float(row["width"].get()) / 100.0),
                    "height": max(0.0, float(row["height"].get()) / 100.0),
                    "asymmetry": max(-1.0, min(1.0, float(row["asymmetry"].get()) / 100.0))
                })
            if not peak_specs:
                self.points = []
                self.user_points = []
                return True
            raw = []
            for index in range(self.MAX_GENERATED_SAMPLES):
                x = index / (self.MAX_GENERATED_SAMPLES - 1)
                y = 0.0
                for peak in peak_specs:
                    effective_width = max(0.002, peak["width"] * (1.0 + abs(asymmetry) * 0.75))
                    peak_asymmetry = max(-1.0, min(1.0, peak["asymmetry"] + asymmetry))
                    y += peak["height"] * self._asymmetric_gaussian(x, peak["center"], effective_width, peak_asymmetry, tail, self._selected_tail_side())
                if height != 0.0:
                    y *= height
                raw.append((x, y))
            maximum = max((value for _, value in raw), default=0.0)
            if maximum > 0.0 and math.isfinite(maximum):
                raw = [(x, max(0.0, min(1.0, y / maximum))) for x, y in raw]
            else:
                raw = [(x, 0.0) for x, _ in raw]
            controls = []
            for peak in peak_specs:
                peak_y = self._linear_interpolate(raw, peak["center"])
                controls.append((peak["center"], peak_y))
                shoulder = max(0.003, peak["width"] * 1.5)
                controls.append((max(0.0, peak["center"] - shoulder), self._linear_interpolate(raw, max(0.0, peak["center"] - shoulder))))
                controls.append((min(1.0, peak["center"] + shoulder), self._linear_interpolate(raw, min(1.0, peak["center"] + shoulder))))
            self.points = self._normalize_points(raw)
            self.user_points = self._normalize_points(controls)
            self.stroke = []
            self.dragged_user_index = None
            self.dragged_user_point = None
            return True
        except (TypeError, ValueError, OverflowError):
            return False

    def _selected_tail_side(self):
        label = self.generator_tail_side_var.get()
        return self._tail_side_key_by_label.get(label, "both")

    @staticmethod
    def _asymmetric_gaussian(x, center, width, asymmetry, tail, tail_side):
        distance = x - center
        sigma = max(0.001, width)
        if asymmetry > 0 and distance > 0:
            sigma *= 1.0 + 0.8 * asymmetry
        elif asymmetry < 0 and distance < 0:
            sigma *= 1.0 + 0.8 * abs(asymmetry)
        if tail > 0:
            shorten = 1.0 - 0.85 * tail
            if tail_side == "left" and distance < 0:
                sigma *= max(0.12, shorten)
            elif tail_side == "right" and distance > 0:
                sigma *= max(0.12, shorten)
            elif tail_side == "both":
                sigma *= max(0.12, shorten)
        sigma = max(0.001, sigma)
        value = math.exp(-0.5 * (distance / sigma) ** 2)
        return value if math.isfinite(value) else 0.0

    def _apply_linear(self):
        self.points = [(0.0, 0.5), (1.0, 0.5)]
        self.user_points = []
        self.stroke = []
        self.dragged_user_index = None
        self.dragged_user_point = None

    def load_distribution(self, distribution):
        self.points = []
        self.user_points = []
        self.stroke = []
        if not isinstance(distribution, (list, tuple)):
            return
        loaded = []
        for point in distribution:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                continue
            x = self._finite_float(point[0])
            y = self._finite_float(point[1])
            if x is None or y is None:
                continue
            loaded.append((max(0.0, min(1.0, x)), max(0.0, min(1.0, y))))
        self.points = self._normalize_points(loaded)
        self.user_points = self._normalize_points(self.points)

    def _validate_distribution(self):
        normalized = self._normalize_points(self.points)
        if not normalized:
            return []
        for x, y in normalized:
            if not math.isfinite(x) or not math.isfinite(y) or x < 0.0 or x > 1.0 or y < 0.0 or y > 1.0:
                return None
        return normalized

    def _normalize_points(self, points):
        if not points:
            return []
        cleaned = []
        for point in points:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                continue
            x = self._finite_float(point[0])
            y = self._finite_float(point[1])
            if x is None or y is None:
                continue
            cleaned.append((max(0.0, min(1.0, x)), max(0.0, min(1.0, y))))
        cleaned.sort(key=lambda item: item[0])
        merged = []
        for x, y in cleaned:
            if merged and abs(merged[-1][0] - x) < self.NORMALIZE_X_THRESHOLD:
                old_x, old_y = merged[-1]
                merged[-1] = ((old_x + x) / 2.0, (old_y + y) / 2.0)
            else:
                merged.append((x, y))
        return merged

    def _find_user_point_near(self, canvas_x, canvas_y):
        best_index = None
        best_distance = self.POINT_HIT_RADIUS_PX
        for index, point in enumerate(self.user_points):
            point_x, point_y = self._normalized_to_canvas(point[0], point[1])
            distance = math.hypot(point_x - canvas_x, point_y - canvas_y)
            if distance <= best_distance:
                best_index = index
                best_distance = distance
        return best_index

    def _logical_buttons_swapped(self):
        candidates = [
            getattr(self.main_app, "swap_mouse_buttons", None),
            getattr(self.main_app, "mouse_buttons_swapped", None),
            getattr(self.main_app, "swap_mouse", None)
        ]
        settings = getattr(getattr(self.main_app, "settings", None), "settings_dict", {})
        if isinstance(settings, dict):
            for section_name in ("Others", "Recordings", "Playback", "Settings"):
                section = settings.get(section_name)
                if isinstance(section, dict):
                    for key in ("Swap_Mouse_Buttons", "Mouse_Buttons_Swapped", "SwapMouseButtons", "Swap_Mouse"):
                        if key in section:
                            candidates.append(section[key])
        return any(value is True for value in candidates)

    def _logical_action_for_event(self, physical_button):
        swapped = self._logical_buttons_swapped()
        if physical_button == 1:
            return "erase" if swapped else "draw"
        return "draw" if swapped else "erase"

    def _on_physical_press(self, event):
        action = self._logical_action_for_event(event.num)
        if action == "draw":
            self._start_drawing(event)
        else:
            self._start_erasing(event)

    def _on_physical_motion(self, event):
        physical_button = 1 if event.state & 0x100 else 3
        action = self._logical_action_for_event(physical_button)
        if action == "draw":
            self._update_drawing(event)
        else:
            self._update_erasing(event)

    def _on_physical_release(self, event):
        action = self._logical_action_for_event(event.num)
        if action == "draw":
            self._finish_drawing(event)
        else:
            self._finish_erasing(event)

    def _start_drawing(self, event):
        point_index = self._find_user_point_near(event.x, event.y)
        self.editing = True
        self.erasing = False
        self.stroke = []
        if point_index is not None:
            self.dragging_point = True
            self.dragged_user_index = point_index
            self.dragged_user_point = self.user_points[point_index]
            return
        self.dragging_point = False
        self.dragged_user_index = None
        self.dragged_user_point = None
        self.stroke = [self._canvas_to_normalized(event.x, event.y)]
        self._merge_stroke_into_curve()
        self._redraw()

    def _update_drawing(self, event):
        if not self.editing or self.erasing:
            return
        if self.dragging_point:
            self._drag_point(event.x, event.y)
            self._redraw()
            return
        point = self._canvas_to_normalized(event.x, event.y)
        if not self.stroke or math.hypot(point[0] - self.stroke[-1][0], point[1] - self.stroke[-1][1]) >= 0.001:
            self.stroke.append(point)
            self._merge_stroke_into_curve()
            self._redraw()

    def _finish_drawing(self, event):
        if not self.editing or self.erasing:
            return
        if self.dragging_point:
            self._drag_point(event.x, event.y)
        else:
            self.stroke.append(self._canvas_to_normalized(event.x, event.y))
            self._merge_stroke_into_curve()
        self.stroke = []
        self.editing = False
        self.dragging_point = False
        self.dragged_user_index = None
        self.dragged_user_point = None
        self.points = self._normalize_points(self.points)
        self.user_points = self._normalize_points(self.user_points)
        self._redraw()

    def _start_erasing(self, event):
        self.editing = True
        self.erasing = True
        self.dragging_point = False
        self.dragged_user_index = None
        self.dragged_user_point = None
        self.stroke = []
        self._erase_at(event.x, event.y)
        self._redraw()

    def _update_erasing(self, event):
        if not self.editing or not self.erasing:
            return
        self._erase_at(event.x, event.y)
        self._redraw()

    def _finish_erasing(self, _event):
        self.stroke = []
        self.editing = False
        self.erasing = False
        self.dragging_point = False
        self.dragged_user_index = None
        self.dragged_user_point = None
        self.points = self._normalize_points(self.points)
        self.user_points = self._normalize_points(self.user_points)
        self._redraw()

    def _drag_point(self, canvas_x, canvas_y):
        if self.dragged_user_index is None or self.dragged_user_index >= len(self.user_points):
            return
        old_point = self.user_points[self.dragged_user_index]
        new_point = self._canvas_to_normalized(canvas_x, canvas_y)
        self.user_points[self.dragged_user_index] = new_point
        self.points = self._replace_curve_point(old_point, new_point)
        normalized_user = self._normalize_points(self.user_points)
        nearest_index = self._find_nearest_normalized_point(normalized_user, new_point)
        self.user_points = normalized_user
        self.dragged_user_index = nearest_index
        self.dragged_user_point = new_point if nearest_index is not None else None

    def _replace_curve_point(self, old_point, new_point):
        if not self.points:
            return [new_point]
        best_index = None
        best_distance = float("inf")
        for index, point in enumerate(self.points):
            distance = math.hypot(point[0] - old_point[0], point[1] - old_point[1])
            if distance < best_distance:
                best_index = index
                best_distance = distance
        if best_index is None:
            return self.points
        updated = self.points.copy()
        updated[best_index] = new_point
        return self._normalize_points(updated)

    @staticmethod
    def _find_nearest_normalized_point(points, target):
        if not points:
            return None
        best_index = 0
        best_distance = float("inf")
        for index, point in enumerate(points):
            distance = math.hypot(point[0] - target[0], point[1] - target[1])
            if distance < best_distance:
                best_index = index
                best_distance = distance
        return best_index

    def _merge_stroke_into_curve(self):
        if not self.stroke:
            return
        stroke = self._normalize_points(self.stroke)
        if not stroke:
            return
        stroke_min = stroke[0][0]
        stroke_max = stroke[-1][0]
        if not self.points:
            self.points = stroke.copy()
            self.user_points = stroke.copy()
            return
        old_points = self.points.copy()
        left_y = self._interpolate(old_points, stroke_min)
        right_y = self._interpolate(old_points, stroke_max)
        retained = [(x, y) for x, y in old_points if x < stroke_min or x > stroke_max]
        if not any(abs(x - stroke_min) < 1e-6 for x, _ in retained):
            retained.append((stroke_min, left_y))
        if not any(abs(x - stroke_max) < 1e-6 for x, _ in retained):
            retained.append((stroke_max, right_y))
        retained.extend(stroke)
        self.points = self._normalize_points(retained)
        self.user_points = self._normalize_points([(x, y) for x, y in self.user_points if x < stroke_min or x > stroke_max] + stroke)

    def _erase_at(self, canvas_x, canvas_y):
        x, y = self._canvas_to_normalized(canvas_x, canvas_y)
        self.points = [(px, py) for px, py in self.points if abs(px - x) > self.ERASE_X_THRESHOLD or abs(py - y) > self.ERASE_Y_THRESHOLD]
        self.user_points = [(px, py) for px, py in self.user_points if abs(px - x) > self.ERASE_X_THRESHOLD or abs(py - y) > self.ERASE_Y_THRESHOLD]

    def _canvas_to_normalized_x(self, canvas_x):
        width = max(1.0, float(self.graph_width))
        fraction = max(0.0, min(1.0, float(canvas_x) / width))
        return self.view_x_min + fraction * (self.view_x_max - self.view_x_min)

    def _canvas_to_normalized_y(self, canvas_y):
        height = max(1.0, float(self.graph_height))
        fraction = max(0.0, min(1.0, float(canvas_y) / height))
        return self.view_y_max - fraction * (self.view_y_max - self.view_y_min)

    def _canvas_to_normalized(self, canvas_x, canvas_y):
        return max(0.0, min(1.0, self._canvas_to_normalized_x(canvas_x))), max(0.0, min(1.0, self._canvas_to_normalized_y(canvas_y)))

    def _normalized_to_canvas(self, x, y):
        x_span = max(1e-9, self.view_x_max - self.view_x_min)
        y_span = max(1e-9, self.view_y_max - self.view_y_min)
        canvas_x = ((x - self.view_x_min) / x_span) * self.graph_width
        canvas_y = (1.0 - ((y - self.view_y_min) / y_span)) * self.graph_height
        return canvas_x, canvas_y

    def _draw_grid(self):
        self.canvas.delete("grid", "axes")
        x_span = self.view_x_max - self.view_x_min
        y_span = self.view_y_max - self.view_y_min
        for index in range(11):
            x = self.graph_width * index / 10.0
            self.canvas.create_line(x, 0, x, self.graph_height, fill=self.GRID_COLOR, tags="grid")
        for index in range(11):
            y = self.graph_height * (1.0 - index / 10.0)
            self.canvas.create_line(0, y, self.graph_width, y, fill=self.GRID_COLOR, tags="grid")
        if self.view_y_min <= 0.0 <= self.view_y_max:
            _, baseline_y = self._normalized_to_canvas(0.0, 0.0)
            self.canvas.create_line(0, baseline_y, self.graph_width, baseline_y, fill=self.BASELINE_COLOR, tags="grid")
        if self.lower_bound <= 0 <= self.upper_bound and self.upper_bound > self.lower_bound:
            zero_normalized_x = (0.0 - self.lower_bound) / (self.upper_bound - self.lower_bound)
            if self.view_x_min <= zero_normalized_x <= self.view_x_max:
                zero_x, _ = self._normalized_to_canvas(zero_normalized_x, 0.0)
                self.canvas.create_line(zero_x, 0, zero_x, self.graph_height, fill=self.ZERO_VERTICAL_AXIS_MARK_COLOR, tags="grid")
        for index, label in enumerate(self.axis_percent_labels):
            normalized_x = self.view_x_min + x_span * index / 4.0
            label.configure(text="%d%%" % round(normalized_x * 100.0))
        self.canvas.create_rectangle(0, 0, self.graph_width - 1, self.graph_height - 1, outline=self.BASELINE_COLOR, tags="axes")

    def _redraw(self):
        if not hasattr(self, "canvas"):
            return
        self.canvas.delete("distribution", "stroke", "points")
        self._draw_grid()
        if self.points:
            render_points = self._get_render_points()
            if len(render_points) == 1:
                x, y = self._normalized_to_canvas(render_points[0][0], render_points[0][1])
                self.canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=self.LINE_COLOR, outline=self.LINE_COLOR, tags="distribution")
            else:
                coords = []
                for x, y in render_points:
                    canvas_x, canvas_y = self._normalized_to_canvas(x, y)
                    if -2 <= canvas_x <= self.graph_width + 2 and -2 <= canvas_y <= self.graph_height + 2:
                        coords.extend((canvas_x, canvas_y))
                if len(coords) >= 4:
                    self.canvas.create_line(*coords, width=3, fill=self.LINE_COLOR, tags="distribution")
        for x, y in self.user_points:
            canvas_x, canvas_y = self._normalized_to_canvas(x, y)
            if -9 <= canvas_x <= self.graph_width + 9 and -9 <= canvas_y <= self.graph_height + 9:
                radius = 4 if self.dragged_user_index is not None else 3
                self.canvas.create_oval(canvas_x - radius, canvas_y - radius, canvas_x + radius, canvas_y + radius, fill=self.POINT_COLOR, outline=self.POINT_COLOR, tags="points")
        if len(self.stroke) >= 2:
            coords = []
            for x, y in self.stroke:
                coords.extend(self._normalized_to_canvas(x, y))
            if len(coords) >= 4:
                self.canvas.create_line(*coords, width=3, dash=(5, 3), fill=self.STROKE_COLOR, tags="stroke")
            for x, y in self.stroke:
                canvas_x, canvas_y = self._normalized_to_canvas(x, y)
                self.canvas.create_oval(canvas_x - 3, canvas_y - 3, canvas_x + 3, canvas_y + 3, fill=self.STROKE_COLOR, outline=self.STROKE_COLOR, tags="stroke")

    def _get_render_points(self):
        if len(self.points) < 2 or self.interpolation_mode == "sharp":
            return self.points
        sample_count = max(64, min(self.MAX_GENERATED_SAMPLES, int(self.graph_width)))
        return [(self.view_x_min + (self.view_x_max - self.view_x_min) * index / (sample_count - 1), self._interpolate(self.points, self.view_x_min + (self.view_x_max - self.view_x_min) * index / (sample_count - 1))) for index in range(sample_count)]

    def _interpolate(self, points, x):
        normalized = self._normalize_points(points)
        if not normalized:
            return 0.0
        if len(normalized) == 1:
            return normalized[0][1]
        if x <= normalized[0][0]:
            return normalized[0][1]
        if x >= normalized[-1][0]:
            return normalized[-1][1]
        for index in range(1, len(normalized)):
            x1, y1 = normalized[index - 1]
            x2, y2 = normalized[index]
            if x <= x2:
                if abs(x2 - x1) < 1e-12:
                    return y2
                if self.interpolation_mode == "sharp":
                    return self._linear_value(x1, y1, x2, y2, x)
                return self._catmull_rom_y(normalized, index - 1, x)
        return normalized[-1][1]

    @staticmethod
    def _linear_value(x1, y1, x2, y2, x):
        amount = (x - x1) / (x2 - x1) if x2 != x1 else 1.0
        return max(0.0, min(1.0, y1 + (y2 - y1) * amount))

    @staticmethod
    def _linear_interpolate(points, x):
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
                return DistributionDrawer._linear_value(x1, y1, x2, y2, x)
        return points[-1][1]

    @staticmethod
    def _catmull_rom_y(points, segment_start_index, x):
        p0 = points[max(0, segment_start_index - 1)]
        p1 = points[segment_start_index]
        p2 = points[min(len(points) - 1, segment_start_index + 1)]
        p3 = points[min(len(points) - 1, segment_start_index + 2)]
        x1, y1 = p1
        x2, y2 = p2
        if abs(x2 - x1) < 1e-12:
            return y2
        t = max(0.0, min(1.0, (x - x1) / (x2 - x1)))
        t2 = t * t
        t3 = t2 * t
        y0 = p0[1]
        y1 = p1[1]
        y2 = p2[1]
        y3 = p3[1]
        value = 0.5 * ((2.0 * y1) + (-y0 + y2) * t + (2.0 * y0 - 5.0 * y1 + 4.0 * y2 - y3) * t2 + (-y0 + 3.0 * y1 - 3.0 * y2 + y3) * t3)
        return max(0.0, min(1.0, value)) if math.isfinite(value) else 0.0

    def interpolate_missing(self):
        if len(self.points) < 2:
            return
        self.points = [(index / (self.MAX_GENERATED_SAMPLES - 1), max(0.0, min(1.0, self._interpolate(self.points, index / (self.MAX_GENERATED_SAMPLES - 1))))) for index in range(self.MAX_GENERATED_SAMPLES)]
        self._redraw()

    def clear(self):
        self.points = []
        self.user_points = []
        self.stroke = []
        self.editing = False
        self.erasing = False
        self.dragging_point = False
        self.dragged_user_index = None
        self.dragged_user_point = None
        self._redraw()

    def _on_mousewheel_zoom(self, event):
        if getattr(event, "num", None) == 4:
            direction = 1
        elif getattr(event, "num", None) == 5:
            direction = -1
        else:
            direction = 1 if getattr(event, "delta", 0) > 0 else -1
        self._zoom_at(self.ZOOM_FACTOR if direction > 0 else 1.0 / self.ZOOM_FACTOR, event.x, event.y)

    def _zoom_in(self):
        self._zoom_at(self.ZOOM_FACTOR, self.graph_width / 2.0, self.graph_height / 2.0)

    def _zoom_out(self):
        self._zoom_at(1.0 / self.ZOOM_FACTOR, self.graph_width / 2.0, self.graph_height / 2.0)

    def _reset_zoom(self):
        self.view_x_min = 0.0
        self.view_x_max = 1.0
        self.view_y_min = 0.0
        self.view_y_max = 1.0
        self._redraw()

    def _zoom_at(self, factor, canvas_x, canvas_y):
        if factor <= 0 or not math.isfinite(factor):
            return
        anchor_x, anchor_y = self._canvas_to_normalized(canvas_x, canvas_y)
        x_span = self.view_x_max - self.view_x_min
        y_span = self.view_y_max - self.view_y_min
        new_x_span = max(self.MIN_VIEW_SPAN, min(1.0, x_span / factor))
        new_y_span = max(self.MIN_VIEW_SPAN, min(1.0, y_span / factor))
        if factor < 1.0:
            new_x_span = min(1.0, x_span / factor)
            new_y_span = min(1.0, y_span / factor)
        self.view_x_min, self.view_x_max = self._centered_view(anchor_x, x_span, new_x_span, self.view_x_min, self.view_x_max)
        self.view_y_min, self.view_y_max = self._centered_view(anchor_y, y_span, new_y_span, self.view_y_min, self.view_y_max)
        self._redraw()

    @staticmethod
    def _centered_view(anchor, old_span, new_span, old_min, old_max):
        if new_span >= 1.0:
            return 0.0, 1.0
        if old_span <= 0:
            old_span = 1.0
        relative = (anchor - old_min) / old_span
        new_min = anchor - relative * new_span
        new_max = new_min + new_span
        if new_min < 0.0:
            new_max -= new_min
            new_min = 0.0
        if new_max > 1.0:
            new_min -= new_max - 1.0
            new_max = 1.0
        return max(0.0, new_min), min(1.0, new_max)

    def apply(self):
        distribution = self._validate_distribution()
        if distribution is None:
            self._safe_messagebox("showerror", self.main_app.text_content["options_menu"]["playback_menu"]["distribution_drawer_settings"]["error"]["invalid_distribution_text"])
            return
        persisted = [
            [round(x, 6), round(y, 6)]
            for x, y in distribution
        ]
        self.owner.distribution = persisted if persisted else None
        self._close_popup()

    def cancel(self):
        self._close_popup()

    def _close_popup(self):
        if self.winfo_exists():
            self.destroy()

    def _set_modal_input_prevention(self, enabled):
        if enabled:
            try:
                self.main_app.prevent_record = True
            except Exception:
                pass
        else:
            self._restore_modal_input_prevention()

    def _restore_modal_input_prevention(self):
        if self._modal_state_restored:
            return
        self._modal_state_restored = True
        try:
            if self._previous_prevent_record is not None:
                self.main_app.prevent_record = self._previous_prevent_record
        except Exception:
            pass

    def _safe_messagebox(self, method, message):
        try:
            getattr(messagebox, method)(self.main_app.text_content["global"]["error"], message, parent=self)
        except Exception:
            pass

    @staticmethod
    def _finite_float(value):
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return number if math.isfinite(number) else None

    @staticmethod
    def _safe_int(value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            return default

    def _clamp_variable(self, variable, minimum, maximum):
        value = self._finite_float(variable.get())
        if value is None:
            variable.set(str(minimum))
            return
        variable.set(self._format_input_number(maximum if value > maximum else minimum if value < minimum else value))

    @staticmethod
    def _format_number(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        if number.is_integer():
            return str(int(number))
        return str(number)

    @staticmethod
    def _format_input_number(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        if number.is_integer():
            return str(int(number))
        return str(number)


