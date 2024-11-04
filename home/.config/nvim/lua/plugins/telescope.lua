return {
  {
    "nvim-telescope/telescope.nvim",
    opts = function()
      -- Hack LazyVim.picker to disable follow flag
      local open_fn = LazyVim.pick.picker.open
      LazyVim.pick.picker.open = function(builtin, opts)
        ---@diagnostic disable-next-line: inject-field
        opts.follow = false
        return open_fn(builtin, opts)
      end
    end,
  },
}
