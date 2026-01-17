class Engine:
    def move_next(self, instance_id):
        # 1. Load current node from DB
        current_node = db.get_current_node(instance_id)

        # 2. Get next node from Definition
        next_node = definition.get_next(current_node)

        # 3. Handle by type
        if next_node.type == "service_task":
            execute_logic(next_node.action)
            self.move_next(instance_id)  # Keep going
        elif next_node.type == "user_task":
            db.save_state(instance_id, next_node.id)
            # STOP: Wait for external signal
