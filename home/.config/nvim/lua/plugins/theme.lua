return {
  {
    "olimorris/onedarkpro.nvim",
    priority = 1000,
    opts = {
      colors = { onedark_dark = { bg = "#202020", gray = "#6b6b6b" } },
      highlights = {
        ["@odp.import_module.python"] = { fg = "#ff9f00" }, -- orange
      },
    },
  },

  -- Configure LazyVim to load colorscheme
  {
    "LazyVim/LazyVim",
    opts = {
      colorscheme = "onedark_dark",
    },
  },
}
