return {
  {
    "nvim-telescope/telescope.nvim",
    opts = function()
      -- Hack LazyVim.picker to disable follow flag
      local open_fn = LazyVim.pick.picker.open
      ---@diagnostic disable-next-line: duplicate-set-field
      LazyVim.pick.picker.open = function(builtin, opt)
        ---@diagnostic disable-next-line: inject-field
        opt.follow = false
        return open_fn(builtin, opt)
      end
    end,
  },
}
