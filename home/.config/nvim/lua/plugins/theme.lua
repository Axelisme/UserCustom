return {
  {
    "olimorris/onedarkpro.nvim",
    priority = 1000,
    opts = {
      colors = { onedark_dark = { bg = "#202020", gray = "#6b6b6b" } },
      highlights = {
        -- disable this to make python import highlight work
        ["@odp.import_module.python"] = {},
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
