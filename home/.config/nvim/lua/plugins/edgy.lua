return {
  "folke/edgy.nvim",
  keys = {
    -- resize windows in terminal mode
    { "<C-Up>", "<cmd>lua require('edgy').get_win():resize('height', 2)<CR>", mode = "t" },
    { "<C-Down>", "<cmd>lua require('edgy').get_win():resize('height', -2)<CR>", mode = "t" },
  },
  init = function()
    -- fix the terminal window not close in first time
    vim.api.nvim_create_autocmd("TermClose", {
      group = vim.api.nvim_create_augroup("term_close", { clear = true }),
      once = true,
      callback = function()
        -- close terminal window in default way
        vim.cmd("q")
      end,
    })
  end,
  opts = function(_, opts)
    opts.animate = { enabled = false }
    opts.wo = { winbar = "" }

    -- disable show buffer and git status in neovim
    opts.left = vim.tbl_filter(function(panel)
      return panel.title == "Neo-Tree Filesystem"
    end, opts.left)
  end,
}
