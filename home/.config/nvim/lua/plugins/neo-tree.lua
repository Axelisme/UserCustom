return {
  {
    "nvim-neo-tree/neo-tree.nvim",
    optional = true,
    keys = {
      {
        "<leader>fe",
        function()
          require("neo-tree.command").execute({ toggle = true, dir = vim.fn.expand("%:p:h") })
        end,
        desc = "Explorer NeoTree (Current File)",
      },
      {
        "<leader>fE",
        function()
          require("neo-tree.command").execute({ toggle = true, dir = LazyVim.root() })
        end,
        desc = "Explorer NeoTree (Root Dir)",
      },
      { "<leader>e", "<leader>fe", desc = "Explorer NeoTree (Current File)", remap = true },
      { "<leader>E", "<leader>fE", desc = "Explorer NeoTree (Root Dir)", remap = true },
    },
    opts = {
      filesystem = {
        bind_to_cwd = false,
        filtered_items = {
          hide_gitignored = false,
          force_visible_in_empty_folder = true,
        },
      },
      commands = {
        toggle_preview_with_image = function(state)
          pcall(require, "image") -- lazy load image.nvim
          require("neo-tree.sources.filesystem.commands").toggle_preview(state)
        end,
      },
      window = {
        mappings = {
          ["<Tab>"] = function(state)
            local current_node = state.tree:get_node() -- this is the current node
            local path = current_node:get_id() -- this gives you the path

            if vim.fn.isdirectory(path) == 1 then
              require("neo-tree.command").execute({ dir = path })
            end
          end,
          ["."] = function(state)
            local current_node = state.tree:get_node() -- this is the current node
            local path = current_node:get_id() -- this gives you the path

            if vim.fn.isdirectory(path) == 1 then
              require("neo-tree.command").execute({ dir = path })
              vim.cmd("cd " .. path)
            end
          end,
          ["P"] = { "toggle_preview_with_image", config = { use_float = true, use_image_nvim = true } },
        },
      },
    },
  },
}
