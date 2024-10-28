return {
  {
    "nvim-lualine/lualine.nvim",
    optional = true,
    opts = function(_, opts)
      table.remove(opts.sections.lualine_c, 1) -- remove root dir
      table.remove(opts.sections.lualine_c, 2) -- remove filetype
      table.insert(opts.sections.lualine_x, "filetype") -- add filetype
    end,
  },
}
