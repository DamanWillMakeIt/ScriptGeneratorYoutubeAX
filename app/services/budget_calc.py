from app.schemas.project import BudgetPlan, CostItem

class BudgetService:
    def calculate_budget(self, limit: float) -> BudgetPlan:
        """
        Calculates a strict budget breakdown.
        Assumption: User owns basic hardware (Camera/Phone/Mic).
        Funds are allocated to: Stock Assets, Props, Locations, Software.
        """
        limit = float(limit)
        
        # --- ZERO BUDGET STRATEGY ---
        if limit <= 0:
            return BudgetPlan(
                total_budget=0.0,
                breakdown=[
                    CostItem(item="Stock Footage", estimated_cost=0, category="Visual", is_essential=True),
                    CostItem(item="Royalty-Free Music", estimated_cost=0, category="Audio", is_essential=True),
                    CostItem(item="Public Locations", estimated_cost=0, category="Location", is_essential=True)
                ],
                recommendations=[
                    "Use Pexels/Pixabay for free stock footage.",
                    "Use YouTube Audio Library for free music.",
                    "Film in public parks or your own home/office."
                ]
            )

        # --- PAID BUDGET STRATEGY (STRICT SPLIT) ---
        breakdown = []
        
        # 1. Visuals & Audio Assets (50% of budget)
        # This covers stock footage subscriptions or one-off purchases
        assets_budget = round(limit * 0.50, 2)
        breakdown.append(CostItem(
            item="Stock Media (Footage/Music)", 
            estimated_cost=assets_budget, 
            category="Visual", 
            is_essential=True
        ))

        # 2. Location & Props (30% of budget)
        # Coffee, entry fees, small props, wardrobe
        loc_budget = round(limit * 0.30, 2)
        breakdown.append(CostItem(
            item="Props & Location Costs (Coffee/Permits)", 
            estimated_cost=loc_budget, 
            category="Location", 
            is_essential=False
        ))
        
        # 3. Software/Tools (20% of budget)
        # Plugins, AI credits, specialized apps
        soft_budget = round(limit * 0.20, 2)
        breakdown.append(CostItem(
            item="Software/Tools/Plugins", 
            estimated_cost=soft_budget, 
            category="Software", 
            is_essential=False
        ))

        # Verification check (handling floating point drift)
        total_calc = assets_budget + loc_budget + soft_budget
        diff = limit - total_calc
        if diff != 0:
            # Add pennies to the biggest category to make it exact
            breakdown[0].estimated_cost += round(diff, 2)

        return BudgetPlan(
            total_budget=limit,
            breakdown=breakdown,
            recommendations=[
                f"Allocate ${assets_budget} for high-quality stock from sites like Storyblocks or Artlist.",
                f"Use the ${loc_budget} for props or buying a coffee to film in a nice cafe.",
                "Focus on 'Soft Costs' (assets) rather than buying new gear."
            ]
        )