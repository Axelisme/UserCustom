local wezterm = require("wezterm")

return {
	-- font
	font = wezterm.font("Fira Code"),
	font_size = 13.0,

	-- tab
	hide_tab_bar_if_only_one_tab = true,

	-- window
	window_background_opacity = 0.85,
	window_padding = {
		left = 0,
		right = 4,
		top = 0,
		bottom = 0,
	},

	-- gpu acceleration
	front_end = "WebGpu",

	-- other
	enable_scroll_bar = true,
}
