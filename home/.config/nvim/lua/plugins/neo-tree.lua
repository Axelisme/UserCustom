return {
  {
    "nvim-neo-tree/neo-tree.nvim",
    opts = {
      filesystem = {
        bind_to_cwd = false,
        filtered_items = {
          hide_gitignored = false,
          force_visible_in_empty_folder = true,
        },
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
        },
      },
      event_handlers = {
        {
          event = "neo_tree_buffer_enter",
          handler = function(_)
            vim.opt.relativenumber = true
          end,
        },
      },
    },
  },
}
