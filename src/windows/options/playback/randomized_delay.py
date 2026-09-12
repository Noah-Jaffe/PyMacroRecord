from tkinter import BOTTOM, LEFT, TOP, Spinbox, messagebox
from tkinter.ttk import Button, Frame, Label
from sys import maxsize as INT_BOUND
from windows.popup import Popup


class RandomizedDelay(Popup):
    def __init__(self, parent, main_app):
        super().__init__(main_app.text_content["options_menu"]["playback_menu"]["randomized_delay_settings"]["title"], 350, 180, parent)
        main_app.prevent_record = True
        self.settings = main_app.settings
        Label(self, text=main_app.text_content["options_menu"]["playback_menu"]["randomized_delay_settings"]["sub_text"], font=("Segoe UI", 10)).pack(side=TOP, pady=10)
        userSettings = main_app.settings.settings_dict
        randomized_delay = userSettings["Playback"].get("Randomized_Delay",{"Enabled": False, "Lower": 0, "Upper": 0})
        inputArea = Frame(self)
        Label(inputArea, text=main_app.text_content["options_menu"]["playback_menu"]["randomized_delay_settings"]["lower_text"]).pack(side=LEFT, padx=5)
        lowerInput = Spinbox(inputArea, from_=-1*INT_BOUND, to=INT_BOUND, width=9, validate="key", validatecommand=(main_app.validate_cmd_float, "%d", "%P"))
        lowerInput.delete(0, "end")
        lowerInput.insert(0, str(randomized_delay.get("Lower", 0)))
        lowerInput.pack(side=LEFT, padx=5)
        Label(inputArea, text=main_app.text_content["options_menu"]["playback_menu"]["randomized_delay_settings"]["upper_text"]).pack(side=LEFT, padx=5)
        upperInput = Spinbox(inputArea, from_=-1*INT_BOUND, to=INT_BOUND, width=9, validate="key", validatecommand=(main_app.validate_cmd_float, "%d", "%P"))
        upperInput.delete(0, "end")
        upperInput.insert(0, str(randomized_delay.get("Upper", 0)))
        upperInput.pack(side=LEFT, padx=5)
        inputArea.pack(pady=10)
        buttonArea = Frame(self)
        Button(buttonArea, text=main_app.text_content["global"]["confirm_button"], command=lambda: self.setNewValues(lowerInput.get(), upperInput.get(), main_app)).pack(side=LEFT, padx=10)
        Button(buttonArea, text=main_app.text_content["global"]["cancel_button"], command=self.destroy).pack(side=LEFT, padx=10)
        buttonArea.pack(side=BOTTOM, pady=10)
        self.update_idletasks()

        popup_width = min(max(350, self.winfo_reqwidth() + 10), 800)
        popup_height = min(max(180, self.winfo_reqheight() + 10), 600)
        self.geometry(f"{popup_width}x{popup_height}")
        self.wait_window()
        main_app.prevent_record = False

    def setNewValues(self, lower_bound, upper_bound, main_app):
        """Function to set the new Randomized Delay numbers""" 
        try:
            lower_bound = float(lower_bound)
            upper_bound = float(upper_bound)
        except ValueError:
            messagebox.showerror(
                main_app.text_content["global"]["error"],
                main_app.text_content["options_menu"]["playback_menu"]["randomized_delay_settings"]["error_new_value"],
            )
            return
        if lower_bound > upper_bound:
            lower_bound, upper_bound = upper_bound, lower_bound
        enabled = lower_bound != 0 or upper_bound != 0
        self.settings.change_settings("Playback", "Randomized_Delay", None, {"Enabled": enabled, "Lower": lower_bound, "Upper": upper_bound})
        self.destroy()