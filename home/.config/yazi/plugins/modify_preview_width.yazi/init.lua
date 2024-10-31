local function toggle_layout(st)
	if st.old_layout then
		Tab.layout, st.old_layout = st.old_layout, nil
	else
		st.old_layout = Tab.layout
		---@diagnostic disable-next-line: duplicate-set-field
		Tab.layout = function(self)
			self._chunks = ui.Layout()
				:direction(ui.Layout.HORIZONTAL)
				:constraints({
					ui.Constraint.Ratio(st.parent, st.all),
					ui.Constraint.Ratio(st.current + st.preview, st.all),
					ui.Constraint.Ratio(0, st.all),
				})
				:split(self._area)
		end
	end
end

local function change_ratio(st, action)
	if st.old_layout then
		-- preview is hidden, ignore action
		return
	end

	if action == "increase" then
		-- increase preview width
		st.current = st.current - st.step / 2
		st.preview = st.preview + st.step / 2
	elseif action == "decrease" then
		-- decrease preview width
		st.current = st.current + st.step / 2
		st.preview = st.preview - st.step / 2
	end

	if st.preview < st.step then
		st.preview = st.step
		st.current = st.all - st.parent - st.preview
	elseif st.current < st.step then
		st.current = st.step
		st.preview = st.all - st.parent - st.current
	end

	---@diagnostic disable-next-line: duplicate-set-field
	Tab.layout = function(self)
		self._chunks = ui.Layout()
			:direction(ui.Layout.HORIZONTAL)
			:constraints({
				ui.Constraint.Percentage(st.parent / st.all * 100),
				ui.Constraint.Percentage(st.current / st.all * 100),
				ui.Constraint.Percentage(st.preview / st.all * 100),
			})
			:split(self._area)
	end
end

local function entry(st, args)
	local action = args[1]
	if not action then
		return
	end

	-- first time initialization
	if not st.step then
		st.parent = MANAGER.ratio.parent
		st.current = MANAGER.ratio.current
		st.preview = MANAGER.ratio.preview
		st.all = st.parent + st.current + st.preview
		st.step = 0.05 * st.all
	end

	if action == "toggle" then
		toggle_layout(st)
	else
		change_ratio(st, action)
	end

	ya.app_emit("resize", {})
end

return { entry = entry }
