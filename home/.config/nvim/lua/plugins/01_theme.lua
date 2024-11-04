return {
  {
    "olimorris/onedarkpro.nvim",
    opts = { colors = { onedark_dark = { bg = "#202020", gray = "#6b6b6b" } } },
  },

  -- Configure LazyVim to load colorscheme
  {
    "LazyVim/LazyVim",
    opts = {
      colorscheme = "onedark_dark",
    },
  },
}
