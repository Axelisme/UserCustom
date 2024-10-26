return {
  { "catppuccin", enabled = false },
  {
    "olimorris/onedarkpro.nvim",
    opts = { colors = { onedark_dark = { bg = "#202020" } } },
  },

  -- Configure LazyVim to load colorscheme
  {
    "LazyVim/LazyVim",
    opts = {
      -- colorscheme = "tokyonight-night",
      colorscheme = "onedark_dark",
    },
  },
}
