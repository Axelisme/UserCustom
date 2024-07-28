return {
  {
    "nvim-neo-tree/neo-tree.nvim",
    opts = {
      filesystem = {
        bind_to_cwd = true,
        filtered_items = {
          force_visible_in_empty_folder = true,
        },
      },
      window = {
        mappings = {
          ["<Tab>"] = function(state)
            local node = state.tree:get_node()
            if require("neo-tree.utils").is_expandable(node) then
              state.commands["toggle_node"](state)
            else
              state.commands["open"](state)
              vim.cmd("Neotree reveal")
            end
          end,
          ["."] = function(state)
            local current_node = state.tree:get_node() -- this is the current node
            local path = current_node:get_id() -- this gives you the path

            if vim.fn.isdirectory(path) == 1 then
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
