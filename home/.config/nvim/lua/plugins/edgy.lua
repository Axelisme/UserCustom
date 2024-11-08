return {
  "folke/edgy.nvim",
  opts = function(_, opts)
    opts.animate = { enabled = false }
    opts.wo = { winbar = "" }

    -- disable show buffer and git status in neovim
    opts.left = vim.tbl_filter(function(panel)
      return panel.title == "Neo-Tree Filesystem"
    end, opts.left)
  end,
}
