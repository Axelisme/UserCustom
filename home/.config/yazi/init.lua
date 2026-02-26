require("git"):setup()
require("modify-preview-width"):entry({ "toggle" })

require("session"):setup({
	sync_yanked = true,
})

-- show user:group in status bar
-- Status:children_add(function()
-- 	local h = cx.active.current.hovered
-- 	if h == nil or ya.target_family() ~= "unix" then
-- 		return ui.Line({})
-- 	end
--
-- 	return ui.Line({
-- 		ui.Span(ya.user_name(h.cha.uid) or tostring(h.cha.uid)):fg("magenta"),
-- 		ui.Span(":"),
-- 		ui.Span(ya.group_name(h.cha.gid) or tostring(h.cha.gid)):fg("magenta"),
-- 		ui.Span(" "),
-- 	})
-- end, 500, Status.RIGHT)
Status:children_add(function()
	local h = cx.active.current.hovered
	if h == nil or ya.target_family() ~= "unix" then
		return ""
	end

	return ui.Line({
		ui.Span(ya.user_name(h.cha.uid) or tostring(h.cha.uid)):fg("magenta"),
		":",
		ui.Span(ya.group_name(h.cha.gid) or tostring(h.cha.gid)):fg("magenta"),
		" ",
	})
end, 500, Status.RIGHT)

-- show ln in status-bar
-- function Status:name()
-- 	local h = self._tab.current.hovered
-- 	if not h then
-- 		return ui.Line({})
-- 	end
--
-- 	-- return ui.Line(" " .. h.name)
-- 	local linked = ""
-- 	if h.link_to ~= nil then
-- 		linked = " -> " .. tostring(h.link_to)
-- 	end
-- 	return ui.Line(" " .. h.name .. linked)
-- end
Status:children_add(function(self)
	local h = self._current.hovered
	if h and h.link_to then
		return " -> " .. tostring(h.link_to)
	else
		return ""
	end
end, 3300, Status.LEFT)
