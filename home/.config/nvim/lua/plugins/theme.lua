return {
  {
    "olimorris/onedarkpro.nvim",
    priority = 1000, -- Ensure it loads first
  },

  -- Configure LazyVim to load catppuccin
  {
    "LazyVim/LazyVim",
    opts = {
      colorscheme = "onedark_vivid",
    },
  },
}
